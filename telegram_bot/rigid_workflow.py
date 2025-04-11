


from typing import Annotated

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

from .prompts import SYSTEM_MESSAGE
from .tools import (
    generate_summary_tool,
    get_unread_chats_tool,
    get_unread_history_tool,
    mark_chats_as_read_tool,
    try_send_message_tool,
)
from .utils import llm

llm_with_tools = llm.bind_tools([get_unread_history_tool, 
                                 try_send_message_tool,
                                 mark_chats_as_read_tool])

# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "tool"]
    messages: Annotated[list, add_messages]
    chats_to_select: list


def route_user_request(state):
    if state['action'] == 'tool':
        return 'tool_node'
    return 'chat_node'


def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return 'tool_node'
    return END

# --- Workflow Nodes ---
async def llm_with_tools_node(state):
    messages = state['messages']
    messages = [SystemMessage(SYSTEM_MESSAGE)] + messages
    response = llm_with_tools.invoke(input=messages)
    state["messages"] += [response]
    return state

async def tool_node(state):
    """
    Execute the tool call from the last message.
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_call = last_message.tool_calls[0]
        tool_name = tool_call["tool"]
        tool_args = tool_call["args"]

        if tool_name == 'get_unread_history_tool':
            if not state.get('unread_chats'):
                unread_chats = await get_unread_chats_tool.invoke(**tool_args)
                state['messages'] += [ToolMessage(unread_chats, name=tool_name)]
            unread_history = await generate_summary_tool(state['unread_chats'])
            state['messages'] += [AIMessage(unread_history)]
        elif tool_name == 'try_send_message_tool':
            result = await try_send_message_tool.invoke(**tool_args)
            if isinstance(result, list):
                state['chats_to_select'] = result
            elif isinstance(result, str):
                state['messages'] += [AIMessage(f"Done")]
        elif tool_name == 'mark_chats_as_read_tool':
            res = await mark_chats_as_read_tool(**tool_args)
            state['messages'] += [AIMessage(f"Done")]
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
    
    workflow.add_conditional_edges(
        START,
        route_user_request,
        ["chat_node",
        "tool_node",]
    )
    workflow.add_edge(START, 'chat_node')
    workflow.add_edge("chat_node", "tool_node")

    return workflow.compile()
