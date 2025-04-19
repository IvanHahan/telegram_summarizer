import os
from contextlib import contextmanager
from typing import Annotated, Union

from langchain.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

from telegram_bot.localization import t

from .prompts import (
    ANALYZE_CHAT_PROMPT_TEMPLATE,
    SUMMARIZE_PROMPT_TEMPLATE,
    SYSTEM_MESSAGE,
)
from .tools import (
    format_chats,
    get_unread_chats_tool,
    mark_chats_as_read_tool,
    search_chat_tool,
    send_message_tool,
    tool,
)
from .utils import create_llm


@tool
def summarize_unread_chats_tool():
    """
    Generate a summary of unread history.
    Always use it to summarize retrieved chat history for user.

    """
    pass


@tool 
def analyze_retrieved_chat_tool():
    """
    Generate analysis of a retrieved chat.
    Always call it when the user asks for chat tone analysis.
    """
    pass

# --- LLM and Tool Setup ---
llm = create_llm()
llm_with_tools = llm.bind_tools([
    get_unread_chats_tool, 
    search_chat_tool, 
    send_message_tool,
    mark_chats_as_read_tool,
    summarize_unread_chats_tool
])

# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary", "mark_as_read", "auth_code", "clear"]
    messages: Annotated[list, add_messages]
    chats_to_select: Union[list, dict]
    selected_chat: dict
    user_id: str
    auth: dict
    unread_chats: list
    thread_id: str

# --- Routing Functions ---
def route_llm_request(state: State) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_name = last_message.tool_calls[0]["name"]
        if tool_name == "summarize_unread_chats_tool":
            return "unread_node"
        elif tool_name == "analyze_retrieved_chat_tool":
            return "analyze_chat_node"
        return "tool_node"
    return END

def route_user_request(state: State) -> str:
    mapping = {"message": "chat_node", "mark_as_read": "mark_as_read_node"}
    return mapping.get(state["action"], END)

# --- Node Functions ---
async def unread_history_node(state: State) -> State:
    user_id = state["user_id"]
    state["messages"].append(HumanMessage(t(user_id, "prompt_unread_question")))
    chats = state.get("unread_chats")
    if not chats:
        chats = await get_unread_chats_tool.ainvoke({"user_id": state["user_id"]})
    state["unread_chats"] = chats
    tool_calls = [{"name": "get_unread_chats_tool",
                   "args": {"user_id": state["user_id"]},
                   "id": "get_unread_chats_tool",
                   'type': 'tool_call'}]
    state["messages"].append(AIMessage(content='',
            tool_calls=tool_calls))
    state["messages"].append(
        ToolMessage(
            name="get_unread_chats_tool",
            content=format_chats(chats),
            tool_call_id="get_unread_chats_tool",
        )
    )
    if not chats:
        state["messages"].append(AIMessage(t(user_id, "no_unread_chats_found")))
        return state
    
    summarization_prompt = PromptTemplate(
        input_variables=["chats", "optional_instruction"],
        template=SUMMARIZE_PROMPT_TEMPLATE,
    ).partial(optional_instruction="")
    response = (summarization_prompt | llm).invoke(input={"chats": format_chats(chats)})
    state["messages"].append(response)
    state["messages"].append(AIMessage(t(user_id, "ask_mark_read")))
    return state

async def analyze_chat_node(state: State) -> State:
    user_id = state["user_id"]
    state["messages"].append(HumanMessage(t(user_id, "analyze_given_chat")))
    chat = state.get("selected_chat")
    if not chat:
        return {"messages": [AIMessage(t(user_id, "no_chat_selected"))]}
    summarization_prompt = PromptTemplate(
        input_variables=["chat"],
        template=ANALYZE_CHAT_PROMPT_TEMPLATE,
    )
    response = (summarization_prompt | llm).invoke(input={"chat": format_chats([chat])})
    state["messages"].append(response)
    return state

async def mark_as_read_node(state: State) -> State:
    user_id = state["user_id"]
    state["messages"].append(HumanMessage(t(user_id, "mark_unread_as_read")))
    unread_chats = state.get("unread_chats")
    if not unread_chats:
        unread_chats = await get_unread_chats_tool.ainvoke({"user_id": state["user_id"]})
    await mark_chats_as_read_tool.ainvoke(
        {"user_id": state["user_id"], "chat_ids": [c["chat_id"] for c in unread_chats]}
    )
    state["unread_chats"] = []
    state["messages"].append(AIMessage(t(user_id, "done")))
    return state

async def select_chat_node(state: State) -> State:
    user_id = state["user_id"]
    chat = state.get("selected_chat", {})
    template = t(user_id, "selected_chat_info")
    msg = template.format(id=chat.get("chat_id"), name=chat.get("chat_name"))
    state["messages"].append(HumanMessage(msg))
    state["messages"].append(AIMessage(t(user_id, "understood")))
    return state

async def clear_state_node(state: State) -> State:
    return {}

async def llm_with_tools_node(state: State) -> State:
    messages = state["messages"]
    system_msgs = [SystemMessage(SYSTEM_MESSAGE)] + messages
    response = llm_with_tools.invoke(input=system_msgs)
    state["messages"].append(response)
    return state

async def tool_node(state: State) -> State:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_call = last_message.tool_calls[0]
        tool_name = tool_call["name"]
        tool_kwargs = tool_call["args"]
        tool_kwargs["user_id"] = state["user_id"]
        tool = next(
            (
                t
                for t in [get_unread_chats_tool, search_chat_tool, send_message_tool]
                if t.name == tool_name
            ),
            None,
        )
        if tool:
            tool_result = await tool.ainvoke(tool_kwargs)
            if tool_name == "search_chat_tool" and isinstance(tool_result, list):
                msg = t(state["user_id"], "chats_to_select_from").format(chats=tool_result)
                state["messages"].append(
                    ToolMessage(
                        name=tool_name,
                        content=msg,
                        tool_call_id=tool_call["id"]
                    )
                )
                state["chats_to_select"] = tool_result
                return state
            elif tool_name == "get_unread_chats_tool":
                state["unread_chats"] = tool_result
                tool_result = format_chats(tool_result)
            state["messages"].append(
                ToolMessage(
                    name=tool_name,
                    content=tool_result,
                    tool_call_id=tool_call["id"]
                )
            )
    return state

# --- Memory Creation ---
@contextmanager
def create_memory(memory_type: str = "redis"):
    """
    Create a memory instance based on the specified type,
    yielding a context‐managed checkpointer.
    """
    if memory_type == "redis":
        mem = RedisSaver.from_conn_string(
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
    else:
        mem = MemorySaver()
    try:
        yield mem
    finally:
        # only RedisSaver needs explicit teardown
        if memory_type == "redis":
            mem.close()

# --- Workflow Setup ---
def chat_workflow(memory: str = os.environ.get("STORE_TYPE", "redis")):
    workflow = StateGraph(State)
    workflow.add_node("chat_node", llm_with_tools_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_node("mark_as_read_node", mark_as_read_node)
    workflow.add_node("unread_node", unread_history_node)
    workflow.add_node("analyze_chat_node", analyze_chat_node)

    workflow.add_edge(START, "chat_node")
    workflow.add_edge("tool_node", "chat_node")
    workflow.add_edge("unread_node", END)
    workflow.add_edge("analyze_chat_node", END)
    workflow.add_edge("mark_as_read_node", END)
    workflow.add_conditional_edges("chat_node", route_llm_request, ["tool_node", "unread_node", "analyze_chat_node", END])

    with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)

async def unread_history_workflow(memory: str = os.environ.get("STORE_TYPE", "redis")):
    workflow = StateGraph(State)
    workflow.add_node("unread_node", unread_history_node)
    workflow.add_edge(START, "unread_node")
    workflow.add_edge("unread_node", END)
    with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)

async def mark_as_read_workflow(memory: str = os.environ.get("STORE_TYPE", "redis")):
    workflow = StateGraph(State)
    workflow.add_node("mark_as_read_node", mark_as_read_node)
    workflow.add_edge(START, "mark_as_read_node")
    workflow.add_edge("mark_as_read_node", END)
    with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)

async def analyze_chat_workflow(memory: str = os.environ.get("STORE_TYPE", "redis")):
    workflow = StateGraph(State)
    workflow.add_node("analyze_chat_node", analyze_chat_node)
    workflow.add_edge(START, "analyze_chat_node")
    workflow.add_edge("analyze_chat_node", END)
    with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)