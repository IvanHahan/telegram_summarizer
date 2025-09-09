from langchain_core.messages import AIMessage, SystemMessage

from ..utils.telegram_utils import (
    create_telegram_client,
    get_chat_history,
    get_unread_chats,
    mark_chats_as_read,
    search_chat,
)
from .data_model import Intent
from .prompts import (
    CHATBOT_SYSTEM_MESSAGE,
    ROUTER_SYSTEM_MESSAGE,
    SUMMARIZE_PROMPT_TEMPLATE,
)
from .state import (
    ChatState,
    MessagesState,
    SummarizeState,
    UnreadHistoryState,
    UserState,
)
from .utils import format_chats, format_messages


def router_node(llm):
    def func(state: MessagesState):
        messages = [SystemMessage(ROUTER_SYSTEM_MESSAGE)] + state["messages"]
        llm_structured = llm.with_structured_output(Intent)
        response = llm_structured.invoke(messages)
        return {
            "intent": response.intent,
            'chat_query': response.chat_name
        }

    return func

def chat_node(llm):
    def func(state: MessagesState):
        response = llm.invoke(
            [SystemMessage(CHATBOT_SYSTEM_MESSAGE)] + state["messages"]
        )
        return {"messages": response}

    return func

async def get_unread_history_node(state: UnreadHistoryState):
    async with create_telegram_client(state['user_id']) as client:
        unread_chats = await get_unread_chats(
            client,
            include_groups=state.get('include_groups', True),
            include_private=state.get('include_private', True),
            include_channels=state.get('include_channels', False),
            include_muted=state.get('include_muted', False)
        )
    history = format_chats(unread_chats)
    return {
        'chat_history': history,
        'chat_ids': [chat['id'] for chat in unread_chats],
    }


def summarize_node(llm):
    def func(state: SummarizeState):
        response = llm.invoke(SUMMARIZE_PROMPT_TEMPLATE.format(chats=state['chat_history']))
        return {"messages": response}

    return func()


def mark_as_read_node(state: ChatState):
    user_id = state["user_id"]
    unread_chats = state.get("chat_ids")

    with create_telegram_client(user_id) as client:
        if not unread_chats:
            unread_chats = get_unread_chats(client)
        mark_chats_as_read(client, unread_chats)

    return {'messages': AIMessage(f"Marked {len(unread_chats)} chats as read.")}


async def search_chat_node(state: UserState):
    user_id = state["user_id"]
    query = state["query"]

    async with create_telegram_client(user_id) as client:
        results = await search_chat(client, query, top_k=5)
        if isinstance(results, list):
            return {"chat_ids": results}
        else:
            return {'chat_id': results['chat_id']}


async def retrieve_chat_node(state: ChatState):
    user_id = state["user_id"]

    assert len(state["chat_ids"]) == 1, "Only one chat ID should be provided."
    chat_id = state["chat_ids"][0]

    async with create_telegram_client(user_id) as client:
        chat_history = await get_chat_history(client, chat_id)
    return {"chat_history": format_messages(chat_history)}


def analyze_chat_node(llm):
    def func(state: ChatState):
        response = llm.invoke(SUMMARIZE_PROMPT_TEMPLATE.format(chats=state['chat_history']))
        return {"messages": response}

    return func()
