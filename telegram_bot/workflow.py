


import os
from typing import Annotated, Union

from langchain.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

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
def summarize_unread_chats_tool(formatted_chats: str):
    """
    Generate a summary of unread history.
    Always call it when the user asks for unread history.
    """
    pass


@tool 
def analyze_retrieved_chat_tool(formatted_chat: str):
    """
    Generate analysis of a retrieved chat.
    Always call it when the user asks for chat analysis.
    """
    pass


llm = create_llm()
llm_with_tools = llm.bind_tools([get_unread_chats_tool, 
                                 search_chat_tool, 
                                 send_message_tool,
                                 mark_chats_as_read_tool,
                                 summarize_unread_chats_tool, 
                                 analyze_retrieved_chat_tool])

# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary", "mark_as_read", 'auth_code', 'clear']
    messages: Annotated[list, add_messages]
    chats_to_select: Union[list, dict]
    selected_chat: dict
    user_id: str
    auth: dict
    unread_chats: list
    thread_id: str

def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if last_message.tool_calls[0]["name"] == "summarize_unread_chats_tool":
            return 'unread_node'
        elif last_message.tool_calls[0]["name"] == "analyze_retrieved_chat_tool":
            return 'analyze_chat_node'
        return 'tool_node'
    
    return END

def route_user_request(state):
    if state['action'] == 'message':
        return 'chat_node'
    elif state['action'] == 'mark_as_read':
        return 'mark_as_read_node'

async def unread_history_node(state):
    state['messages'].append(HumanMessage('What I missed?'))
    unread_chats = state.get('unread_chats')
    if not unread_chats:
        chats = await get_unread_chats_tool.ainvoke({'user_id': state['user_id']})
        
    state['unread_chats'] = chats
    state['messages'].append(ToolMessage(name='get_unread_chats_tool', content=format_chats(chats), tool_call_id='get_unread_chats_tool'))
    summarization_prompt = PromptTemplate(
        input_variables=["chats", "optional_instruction"],
        template=SUMMARIZE_PROMPT_TEMPLATE
    ).partial(optional_instruction="")

    response = (summarization_prompt | llm).invoke(input={'chats': format_chats(chats)})
    state['messages'] += [response]
    state['messages'].append(AIMessage("Would you like to mark messages as read?"))
    return state

async def analyze_chat_node(state):
    state['messages'].append(HumanMessage('Analyze given chat'))
    chat = state.get('selected_chat')
    if not chat:
        return {'messages': [AIMessage("No chat selected for analysis.")]}
    
    summarization_prompt = PromptTemplate(
        input_variables=["chat"],
        template=ANALYZE_CHAT_PROMPT_TEMPLATE
    )

    response = (summarization_prompt | llm).invoke(input={'chat': format_chats([chat])})
    return {'messages': [response]}

async def mark_as_read_node(state):
    unread_chats = state.get('unread_chats')
    state['messages'].append(HumanMessage('Mark unread as read'))
    if not unread_chats:
        unread_chats = await get_unread_chats_tool.ainvoke({'user_id': state['user_id']})
    
    await mark_chats_as_read_tool.ainvoke({'user_id': state['user_id'], 
                                    'chat_ids': [c['chat_id'] for c in unread_chats]})
    state['unread_chats'] = []
    state['messages'].append(AIMessage('Done!'))
    return state

async def select_chat_node(state):
    chat = state['selected_chat']
    state['messages'].append(HumanMessage(f"Selected with ID: {chat['chad_id']} and name: {chat['chad_name']}"))
    state['messages'].append(AIMessage("Understood!"))

async def clear_state_node(state):
    return dict()

# --- Workflow Nodes ---
async def llm_with_tools_node(state):
    
    messages = state['messages']
    if isinstance(state['messages'][-1], ToolMessage) and state['messages'][-1].name == 'get_unread_chats_tool':
        messages[-1].content = SUMMARIZE_PROMPT_TEMPLATE.format(chats=messages[-1].content)
    if isinstance(state['messages'][-1], ToolMessage) and state['messages'][-1].name == 'search_chat_tool':
        return state
    messages = [SystemMessage(SYSTEM_MESSAGE)] + messages
    response = llm_with_tools.invoke(input=messages)
    state["messages"] += [response]
    return state

async def tool_node(state):
    """
    Execute a tool based on the last message's tool call.
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_call = last_message.tool_calls[0]
        tool_name = tool_call["name"]
        tool_kwargs = tool_call["args"]
        tool_kwargs['user_id'] = state['user_id']

        # Find the tool by name and invoke it
        tool = next((t for t in [get_unread_chats_tool, search_chat_tool, send_message_tool] if t.name == tool_name), None)
        if tool:
            tool_result = await tool.ainvoke(tool_kwargs)
            state["messages"] += [ToolMessage(name=tool_name, content=str(tool_result), tool_call_id=tool_call['id'])]
            if tool_name == 'search_chat_tool' and isinstance(tool_result, list):
                state['chats_to_select'] = tool_result
            elif tool_name == 'get_unread_chats_tool':
                state['unread_chats'] = tool_result
    return state

def create_memory(memory_type: str = "redis"):
    """
    Create a memory instance based on the specified type.
    """
    if memory_type == "redis":
        return AsyncRedisSaver.from_conn_string(
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    elif memory_type == "memory_saver":
        return MemorySaver()


# --- Workflow Setup ---
async def chat_workflow(memory='redis'):
    """
    Create and compile the workflow for processing unread messages and summarizing them.
    """
    workflow = StateGraph(State)
    workflow.add_node("chat_node", llm_with_tools_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_node("mark_as_read_node", mark_as_read_node)
    workflow.add_node("unread_node", unread_history_node)
    workflow.add_node("analyze_chat_node", analyze_chat_node)

    workflow.add_edge(START, "chat_node")
    workflow.add_edge("tool_node", "chat_node")
    workflow.add_edge('unread_node', END)
    workflow.add_edge('analyze_chat_node', END)
    workflow.add_edge('mark_as_read_node', END)
    workflow.add_conditional_edges(
        "chat_node",
        route_llm_request,
        ["tool_node", END],
    )

    workflow.add_conditional_edges(
        "chat_node",
        route_llm_request,
        ["tool_node", 'unread_node', 'analyze_chat_node', END],
    )

    async with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)#, store=memory)


async def unread_history_workflow(memory='redis'):
    """
    Create and compile the workflow for processing unread messages and summarizing them.
    """
    workflow = StateGraph(State)
    workflow.add_node("unread_node", unread_history_node)
    
    workflow.add_edge(START, "unread_node")
    workflow.add_edge('unread_node', END)
    
    async with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)#, store=memory)

async def mark_as_read_workflow(memory='redis'):
    """
    Create and compile the workflow for processing unread messages and summarizing them.
    """
    workflow = StateGraph(State)
    workflow.add_node("mark_as_read_node", mark_as_read_node)
    
    workflow.add_edge(START, "mark_as_read_node")
    workflow.add_edge('mark_as_read_node', END)
    
    async with create_memory(memory) as checkpointer:
        return workflow.compile(checkpointer=checkpointer)#, store=memory)

async def analyze_chat_workflow():
    """
    Create and compile the workflow for analyzing a chat.
    """
    workflow = StateGraph(State)
    workflow.add_node("analyze_chat_node", analyze_chat_node)
    
    workflow.add_edge(START, "analyze_chat_node")
    workflow.add_edge('analyze_chat_node', END)
    
    async with create_memory() as checkpointer:
        return workflow.compile(checkpointer=checkpointer)#, store=memory)