


from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

from .prompts import SUMMARIZE_PROMPT_TEMPLATE, SYSTEM_MESSAGE
from .tools import get_unread_chats_tool, search_chat_tool
from .utils import create_llm, format_chats

llm = create_llm()
llm_with_tools = llm.bind_tools([get_unread_chats_tool, search_chat_tool])

def route_user_request(state):
    if state['action'] == 'unread_summary':
        return "unread_messages_node"
    elif state['action'] == 'message':
        return "chat_node"
        


def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if last_message.tool_calls[0]['name'] == "get_unread_chats_tool":
            if 'unread_chats' in state and state['unread_chats']:
                return 'summarize_node'
            else:
                return "unread_messages_node"
    return END


# --- Workflow Nodes ---
def chat_node(state):
    messages = state['messages']
    messages = [SystemMessage(SYSTEM_MESSAGE)] + messages
    response = llm_with_tools.invoke(input=messages)
    state["messages"] += [response]
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