from typing import Annotated, Union

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


# --- State Definition ---
class State(TypedDict):
    messages: Annotated[list, add_messages]
    chats_to_select: Union[list, dict]
    selected_chat: dict
    user_id: str
    unread_chats: list