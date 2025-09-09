from langgraph.graph import END

from .state import ChatState, RouteState


def route_request(state: RouteState):
    intent = state["intent"]
    chat_query = state.get('chat_query')
    if chat_query:
        return 'search_chat_node'
    if intent == 'SUMMARY':
        return "summary_node"
    elif intent == 'MARK_AS_READ':
        return "mark_as_read_node"
    elif intent == 'ANALYZE':
        return END
    return 'chat_node'


def search_chat_route(state: ChatState):
    if len(state['chat_ids']) > 1:
        return END
    elif len(state['chat_ids']) == 1:
        return "retrieve_chat_node"
    raise ValueError("No chat selected or chat ID provided.")

def retrieve_chat_route(state: RouteState):
    if state['intent'] == 'ANALYZE':
        return "analyze_chat_node"
    elif state['intent'] == 'SUMMARY':
        return "summarize_node"
    elif state['intent'] == 'MARK_AS_READ':
        return "mark_as_read_node"
    raise ValueError("Invalid intent for chat retrieval.")