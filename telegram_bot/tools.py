from langchain.tools import tool

from telegram_bot.telegram_utils import (
    create_telegram_client,
    get_chat_history,
    get_unread_chats,
    mark_chats_as_read,
    search_chat,
    send_message,
)


@tool
async def get_unread_chats_tool(user_id: str, include_groups=True, include_private=True, include_channels=True, include_muted=False) -> list:
    """
    Fetch unread chats from Telegram, including groups, private chats, and channels. 
    Call this tool only if the user requests it.
    Must be used together with summarization tool to summarize the unread messages.

    Args:
        user_id (str): The ID of the user. Can be ignored
        include_groups (bool): If True, include group chats in the results.
        include_private (bool): If True, include private chats in the results.
        include_channels (bool): If True, include channels, news channels in the results.
        include_muted (bool): If True, include muted chats in the results. 
                              Muted chats are those for which notifications are disabled.
    Returns:
        list: A list of unread chats with their details, filtered based on the provided arguments.
    """
    async with create_telegram_client(user_id) as client:
        unread_chats = await get_unread_chats(
            client,
            include_groups=include_groups,
            include_private=include_private,
            include_channels=include_channels,
            include_muted=include_muted
        )
    return unread_chats


@tool
async def search_chat_tool(user_id: str, query: str, top_k: int = 5):
    """
    Use when you need to retrieve chat ID.
    If it returns a list of chats, User must select the one.

    Args:
        user_id (str): The ID of the user. Can be ignored
        query (str or int): The name or ID of the chat to search for.
        top_k (int): The number of top similar chats to return if the query is a string.
    """
    async with create_telegram_client(user_id) as client:
        results = await search_chat(client, query, top_k=top_k)
    return results


@tool
async def get_chat_history_tool(user_id: str, chat_id: int) -> list:
    """
    Fetch the message history of a specific chat.

    Args:
        user_id (str): The ID of the user. Can be ignored
        chat_id (int): The ID of the chat to fetch the history from.
        limit (int): The maximum number of messages to retrieve. Defaults to 100.

    Returns:
        list: A list of messages from the chat history.
    """
    async with create_telegram_client(user_id) as client:
        messages = await get_chat_history(client, chat_id, hours=24, max_words=10000)
    return messages


@tool
async def send_message_tool(user_id: str, chat_id: int, message: str) -> str:
    """
    Use to send a message to a specific chat by its ID.
    Use search_chat_tool to find the chat ID before using this tool if not found.

    Args:
        user_id (str): The ID of the user. Can be ignored
        chat_id (int): The ID of the chat to send the message to.
        message (str): The message content to send.

    Returns:
        str: A confirmation message indicating the result of the operation.
    """
    async with create_telegram_client(user_id) as client:
        await send_message(client, chat_id, message)
    return f"Message sent to chat ID {chat_id}."

@tool
async def mark_chats_as_read_tool(user_id: str, chat_ids: list) -> str:
    """
    Mark the specified chats as read.

    Args:
        user_id (str): The ID of the user. Can be ignored
        chat_ids (list): A list of chat IDs to mark as read.

    Returns:
        str: A confirmation message indicating the result of the operation.
    """
    async with create_telegram_client(user_id) as client:
        await mark_chats_as_read(client, chat_ids)
    return f"Marked {len(chat_ids)} chats as read."