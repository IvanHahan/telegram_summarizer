


from typing import Annotated

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from typing_extensions import Literal, TypedDict

from .prompts import SUMMARIZE_PROMPT_TEMPLATE, SYSTEM_MESSAGE
from .tools import get_unread_chats_tool, search_chat_tool, send_message_tool
from .utils import format_chats, llm

llm_with_tools = llm.bind_tools([get_unread_chats_tool, 
                                 search_chat_tool, 
                                 send_message_tool])
agent = create_react_agent(llm, 
                            tools=[get_unread_chats_tool, 
                                   search_chat_tool, 
                                   send_message_tool])


# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary"]
    messages: Annotated[list, add_messages]
    unread_chats: list
    current_chat_id: str
    current_chat: list
    chats_to_select: list


def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return 'tool_node'
    return END

# --- Workflow Nodes ---
async def llm_with_tools_node(state):
    messages = state['messages']
    if isinstance(state['messages'][-1], ToolMessage) and state['messages'][-1].name == 'get_unread_chats_tool':
        messages[-1].content = SUMMARIZE_PROMPT_TEMPLATE.format(chats=messages[-1].content)
    if isinstance(state['messages'][-1], ToolMessage) and state['messages'][-1].name == 'search_chat_tool':
        state['chats_to_select'] = messages[-1].content
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
            state["messages"] += [ToolMessage(name=tool_name, content=tool_result, tool_call_id=tool_call['id'])]
    return state

async def unread_messages_node(state):
    """
    Extract unread messages from Telegram chats.
    """
    last_message = state["messages"][-1]
    kwargs = {}
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        kwargs = last_message.tool_calls[0]['args']
    unread_chats = await get_unread_chats_tool.ainvoke(kwargs)

    state['unread_chats'] = unread_chats
    return state

def summarize_node(state):
    """
    Summarize unread messages using the LLM.
    """
    def func():
        global limit_context_error
        unread_chats = state['unread_chats']
        if state['messages']:
            state['messages'][-1] = AIMessage(format_chats(unread_chats))
        else:
            state['messages'] = [AIMessage(format_chats(unread_chats))]
        messages = [SystemMessage(SYSTEM_MESSAGE)] + state['messages'] + [HumanMessage(SUMMARIZE_PROMPT_TEMPLATE)]
        try:
            return llm.invoke(input=messages)
        except Exception as e:
            if e.code == 'context_length_exceeded':
                if len(state['unread_chats']) < 5:
                    for chat in state['unread_chats']:
                        chat['unread_messages'] = chat['unread_messages'][:len(chat['unread_messages'])//2]
                state['unread_chats'] = state['unread_chats'][:len(state['unread_chats'])//2]
                response = func()
                limit_context_error = True
                return response
    
    limit_context_error = False
    response = func()
    if limit_context_error:
        state['messages'][-1] = AIMessage(f"Context length exceeded. Here is a partial summary:\n{response.content}")
    state['messages'] += [response]
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
