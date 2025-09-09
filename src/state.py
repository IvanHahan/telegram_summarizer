from typing import Annotated, Union

from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


# --- State Definition ---
class State(MessagesState):
    messages: Annotated[list, add_messages]
    chats_to_select: Union[list, dict]
    selected_chat: dict
    user_id: str
    unread_chats: list


class RouteState(TypedDict):
    intent: str
    chat_query: str

class UnreadHistoryState(TypedDict):
    user_id: str
    include_groups: bool
    include_private: bool
    include_channels: bool
    include_muted: bool


class ChatState(TypedDict):
    user_id: str
    chat_query: str
    chat_ids: list[str]
    chat_history: str
