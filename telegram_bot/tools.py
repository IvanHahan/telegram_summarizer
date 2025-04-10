from langchain.prompts import PromptTemplate
from langchain.tools import tool

from telegram_bot.telegram_utils import (
    create_telegram_client,
    get_unread_chats,
    search_chat,
    send_message,
)

from .prompts import SUMMARIZE_PROMPT_TEMPLATE
from .utils import format_chats, llm


@tool
async def get_unread_chats_tool(include_groups=True, include_private=True, include_channels=True, include_muted=False) -> list:
    """
    Fetch unread chats from Telegram, including groups, private chats, and channels. 
    Call this tool only if the user requests it.
    Must be used together with summarization tool to summarize the unread messages.

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
async def search_chat_tool(query: str, top_k: int = 5):
    """
    Use when you need to retrieve chat ID.

    Args:
        query (str or int): The name or ID of the chat to search for.
        top_k (int): The number of top similar chats to return if the query is a string.
    """
    async with create_telegram_client() as client:
        results = await search_chat(client, query, top_k=top_k)
    return results


@tool
async def send_message_tool(chat_id: int, message: str) -> str:
    """
    Use to send a message to a specific chat by its ID.
    Use search_chat_tool to find the chat ID before using this tool if not found.

    Args:
        chat_id (int): The ID of the chat to send the message to.
        message (str): The message content to send.

    Returns:
        str: A confirmation message indicating the result of the operation.
    """
    async with create_telegram_client() as client:
        await send_message(client, chat_id, message)
    return f"Message sent to chat ID {chat_id}."


@tool
async def generate_summary_tool(chats: list) -> str:
    """
    Generate a summary for the given chats.
    Always use this tool after the get_unread_chats_tool to summarize the unread messages.

    Args:
        chats (list): A list of chat objects ready for summary generation.

    Returns:
        str: The generated summary.
    """
    summarization_prompt = PromptTemplate(
        input_variables=["chats", "optional_instruction"],
        template=SUMMARIZE_PROMPT_TEMPLATE
    ).partial(optional_instruction="")
    limit_context_error = False

    def func(chats, summarization_prompt):
        nonlocal limit_context_error  # Use nonlocal to modify the variable in the enclosing scope
        try:
            return (summarization_prompt | llm).invoke(input={'chats': format_chats(chats)})
        except Exception as e:
            if e.code == 'context_length_exceeded':
                if len(chats) < 5:
                    for chat in chats:
                        chat['unread_messages'] = chat['unread_messages'][:len(chat['unread_messages']) // 2]
                chats = chats[:len(chats) // 2]
                limit_context_error = True
                summarization_prompt = summarization_prompt.partial(
                    optional_instruction="Inform user that this is a partial summary due to context limitations"
                )
                return func(chats, summarization_prompt)

    response = func(chats, summarization_prompt)
    return response