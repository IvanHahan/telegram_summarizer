


from typing import Annotated, Union

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

from .prompts import SUMMARIZE_PROMPT_TEMPLATE, SYSTEM_MESSAGE
from .telegram_utils import create_telegram_client
from .tools import (
    get_unread_chats_tool,
    mark_chats_as_read_tool,
    search_chat_tool,
    send_message_tool,
)
from .utils import llm


# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary"]
    messages: Annotated[list, add_messages]
    chats_to_select: Union[list, dict]
    user_id: str
    unread_chats: list

def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return 'tool_node'
    return END

# --- Workflow Nodes ---
async def llm_with_tools_node(state):
    client = create_telegram_client(state['user_id'])
    llm_with_tools = llm.bind_tools([get_unread_chats_tool.bind(client), 
                                 search_chat_tool.bind(client), 
                                 send_message_tool.bind(client),
                                 mark_chats_as_read_tool.bind(client)])
    
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
        tool_args = tool_call["args"]

        # Find the tool by name and invoke it
        tool = next((t for t in [get_unread_chats_tool, search_chat_tool, send_message_tool] if t.name == tool_name), None)
        if tool:
            tool_result = await tool.ainvoke(tool_args)
            state["messages"] += [ToolMessage(name=tool_name, content=str(tool_result), tool_call_id=tool_call['id'])]
            if tool_name == 'search_chat_tool' and isinstance(tool_result, list):
                state['chats_to_select'] = tool_result
            elif tool_name == 'get_unread_chats_tool':
                state['unread_chats'] = tool_result
    return state


# --- Workflow Setup ---
def create_workflow():
    """
    Create and compile the workflow for processing unread messages and summarizing them.
    """
    memory = MemorySaver()
    workflow = StateGraph(State)
    workflow.add_node("chat_node", llm_with_tools_node)
    workflow.add_node("tool_node", tool_node)
    
    workflow.add_edge(START, 'chat_node')
    workflow.add_edge("tool_node", "chat_node")
    workflow.add_conditional_edges(
        "chat_node",
        route_llm_request,
        ["tool_node", END],
    )


    return workflow.compile()
