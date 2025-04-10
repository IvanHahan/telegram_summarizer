
from langchain.tools import tool

from telegram_bot.telegram_utils import (
    create_telegram_client,
    get_unread_chats,
    search_chat,
)


@tool
async def get_unread_chats_tool(include_groups=True, include_private=True, include_channels=True, include_muted=False) -> list:
    """
    Fetch unread chats from Telegram, including groups, private chats, and channels. 
    Call this tool only if the user requests it.

    Args:
        include_groups (bool): If True, include group chats in the results.
        include_private (bool): If True, include private chats in the results.
        include_channels (bool): If True, include channels, news channels in the results.
        include_muted (bool): If True, include muted chats in the results. 
                              Muted chats are those for which notifications are disabled.
    Returns:
        list: A list of unread chats with their details, filtered based on the provided arguments.
    """
    async with create_telegram_client() as client:
        unread_chats = await get_unread_chats(
            client,
            include_groups=include_groups,
            include_private=include_private,
            include_channels=include_channels,
            include_muted=include_muted
        )
    return unread_chats


@tool
async def search_chat_tool(query: str, top_k: int = 3) -> list:
    """
    Search for a chat by name or ID. If the query is a string, find the top-k similar dialogs.

    Args:
        query (str or int): The name or ID of the chat to search for.
        top_k (int): The number of top similar chats to return if the query is a string.

    Returns:
        list: A list of dictionaries containing chat details for the top-k matches, or a single match if the query is an ID.
    """
    async with create_telegram_client() as client:
        results = await search_chat(client, query, top_k=top_k)
    return results