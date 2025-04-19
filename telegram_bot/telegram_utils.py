import os
from datetime import datetime, timezone
from difflib import SequenceMatcher

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")

async def get_unread_chats(
    client, 
    include_private=True, 
    include_groups=False, 
    include_channels=False, 
    include_muted=False, 
    max_unread_count=20,
    max_days=3,
    max_chats: int = 10,
    max_words: int = 10000
):
    """
    Extract unread messages from private chats, group chats, and/or channels based on the provided flags.
    
    Args:
        client (TelegramClient): An instance of the TelegramClient.
        include_private (bool): Whether to include private chats in the results.
        include_groups (bool): Whether to include group chats in the results.
        include_channels (bool): Whether to include channels in the results.
        include_muted (bool): Whether to include muted chats and channels in the results.
        max_unread_count (int, optional): Maximum number of unread messages to extract per chat.
        max_days (int): Maximum number of days to look back for messages.
        max_chats (int, optional): Maximum number of chats to return. If None, return all matching chats.
        max_words (int, optional): Maximum total number of words across all extracted messages.
    
    Returns:
        list: A list of dictionaries containing chat names, unread message counts, and unread messages.
    """
    unread_chats = []
    dialogs = await client.get_dialogs()
    total_words = 0  # Global counter for words among all messages

    for dialog in dialogs:
        if max_chats is not None and len(unread_chats) >= max_chats:
            break

        if dialog.unread_count > 0:  # Check if the chat has unread messages
            # Check if the chat is muted
            is_muted = dialog.dialog.notify_settings and dialog.dialog.notify_settings.mute_until and dialog.dialog.notify_settings.mute_until > datetime.now(timezone.utc)
            if not include_muted and is_muted:
                continue
            
            if (include_private and dialog.is_user) or \
               (include_groups and dialog.is_group) or \
               (include_channels and dialog.is_channel):
                # Fetch unread messages
                unread_messages = []
                limit_messages = min(max_unread_count, dialog.unread_count)
                async for message in client.iter_messages(dialog.id, limit=limit_messages):
                    # Stop processing if message is too old
                    if (datetime.now(timezone.utc) - message.date).days > max_days:
                        continue
                    
                    if not message.text:
                        continue

                    # Count words in the message
                    words_in_message = len(message.text.split())
                    # If max_words is set and adding this message would exceed the limit, break out
                    if max_words is not None and (total_words + words_in_message) > max_words:
                        # Optionally, you could trim the message text to include only remaining allowed words:
                        # remaining = max_words - total_words
                        # trimmed_text = " ".join(message.text.split()[:remaining])
                        # unread_messages.append({ "text": trimmed_text, ... })
                        break  # Stop processing further messages in this dialog
                    
                    total_words += words_in_message
                    
                    sender_name = None
                    if message.sender and hasattr(message.sender, 'first_name'):
                        sender_name = message.sender.first_name or message.sender.last_name or message.sender.username
                    entry = {
                        "text": message.text,
                        "sender_id": message.sender_id,
                    }
                    if sender_name:
                        entry["sender_name"] = sender_name
                    unread_messages.append(entry)
                
                # If any messages were collected, add chat info
                if unread_messages:
                    unread_chats.append({
                        "chat_name": dialog.name,
                        "chat_id": dialog.id,
                        "unread_count": dialog.unread_count,
                        "messages": unread_messages,
                        "is_channel": dialog.is_channel,
                        "is_group": dialog.is_group,
                    })
                    
                # If we've reached the overall word limit, break out of processing further dialogs.
                if max_words is not None and total_words >= max_words:
                    break

    return unread_chats

async def get_chat_history(client, chat_id, hours=10, max_words: int = None):
    """
    Retrieve the message history of a specific chat within a given number of hours.

    Args:
        client (TelegramClient): An instance of the TelegramClient.
        chat_id (int or str): The ID or username of the chat to retrieve the history from.
        hours (int): The maximum number of hours to look back for messages.
        max_words (int, optional): Maximum total number of words across all returned messages.
    Returns:
        list: A list of dictionaries containing message details.
    """
    messages = []
    total_words = 0  # global word counter
    async for message in client.iter_messages(chat_id):
        # stop if message is older than the specified hours window
        if (datetime.now(timezone.utc) - message.date).seconds > (hours * 3600):
            break 
        # enforce max_words limit
        text = message.text or ""
        if max_words is not None:
            words_in_msg = len(text.split())
            if total_words + words_in_msg > max_words:
                break
            total_words += words_in_msg

        sender_name = None
        if message.sender and hasattr(message.sender, 'first_name'):
            sender_name = message.sender.first_name or message.sender.last_name or message.sender.username
        messages.append({
            "text": text,
            "sender_id": message.sender_id,
            "date": message.date,
        })
        if sender_name:
            messages[-1]["sender_name"] = sender_name
    return messages

async def mark_chats_as_read(client, chat_ids):
    """
    Mark the given chats as read.

    Args:
        client (TelegramClient): An instance of the TelegramClient.
        chat_ids (list): A list of chat IDs to mark as read.

    Returns:
        None
    """
    for chat_id in chat_ids:
        await client.send_read_acknowledge(chat_id)

def bigram_similarity(query: str, target: str) -> float:
    """
    Calculate the similarity between two strings using bigrams and intersection.

    Args:
        query (str): The query string.
        target (str): The target string to compare against.

    Returns:
        float: A similarity score between 0 and 1.
    """
    def get_bigrams(text: str) -> set:
        """Generate a set of bigrams from a string."""
        text = text.lower()
        return {text[i:i+2] for i in range(len(text) - 1)}

    query_bigrams = get_bigrams(query)
    target_bigrams = get_bigrams(target)

    intersection = query_bigrams & target_bigrams
    union = query_bigrams | target_bigrams

    return len(intersection) / len(query_bigrams) if union else 0.0


async def search_chat(client, query, top_k=3):
    """
    Search for a chat by name or ID. If the query is a string, find the top-k similar dialogs using bigram similarity.

    Args:
        client (TelegramClient): An instance of the TelegramClient.
        query (str or int): The name or ID of the chat to search for.
        top_k (int): The number of top similar chats to return if the query is a string.

    Returns:
        list: A list of dictionaries containing chat details for the top-k matches, or a single match if the query is an ID.
    """
    dialogs = await client.get_dialogs()
    results = []

    if isinstance(query, str):
        # Calculate bigram similarity for each dialog name
        for dialog in dialogs:
            similarity = SequenceMatcher(None, query.lower(), dialog.name.lower()).ratio()
            results.append({
                "chat_name": dialog.name,
                "chat_id": dialog.id,
                "is_channel": dialog.is_channel,
                "is_group": dialog.is_group,
                "unread_count": dialog.unread_count,
                "similarity": similarity,
            })

        # Sort results by similarity in descending order and return the top-k
        results = sorted(results, key=lambda x: x["similarity"], reverse=True)[:top_k]
        if results[0]["similarity"] == 1:
            return results[0]  # Return the best match if it's an exact match
        return results

    elif isinstance(query, int):
        # Match by chat ID
        for dialog in dialogs:
            if dialog.id == query:
                return {
                    "chat_name": dialog.name,
                    "chat_id": dialog.id,
                    "is_channel": dialog.is_channel,
                    "is_group": dialog.is_group,
                    "unread_count": dialog.unread_count,
                }

    return None  # Return an empty list if no match is found

async def send_message(client, chat_id, message):
    """
    Send a message to a specific chat.

    Args:
        client (TelegramClient): An instance of the TelegramClient.
        chat_id (int or str): The ID or username of the chat to send the message to.
        message (str): The message text to send.

    Returns:
        Message: The sent message object.
    """
    try:
        sent_message = await client.send_message(chat_id, message)
        return sent_message
    except Exception as e:
        print(f"Failed to send message to chat {chat_id}: {e}")
        return None

def create_telegram_client(session_name="session_name", api_id=api_id, api_hash=api_hash):
    """
    Create and return a Telegram client instance.
    
    Args:
        session_name (str): The name of the session file to use for the client.
    
    Returns:
        TelegramClient: An instance of the TelegramClient.
    """
    if not api_id or not api_hash:
        raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in the environment variables.")
    
    client = TelegramClient(str(session_name), api_id, api_hash)
    return client

async def is_authorized(user_id: str):
    client = create_telegram_client(user_id)
    await client.connect()
    res = await client.is_user_authorized()
    await client.disconnect()
    return res

if __name__ == "__main__":
    # Example usage
    with create_telegram_client() as client:
        print("Telegram client created successfully!")

        # Extract only private chats, excluding muted ones, with a maximum of 5 unread messages per chat
        unread_private_chats = get_unread_chats(client, include_private=True, include_groups=False, include_channels=False, include_muted=False, max_unread_count=5)
        print("Unread private chats (excluding muted, max 5 messages):")
        for chat in unread_private_chats:
            print(f"Private Chat: {chat['chat_name']}, Unread messages: {chat['unread_count']}")
            for message in chat['unread_messages']:
                print(f"  - {message}")

        # Extract only group chats
        unread_group_chats = get_unread_chats(client, include_private=False, include_groups=True, include_channels=False)
        print("\nUnread group chats:")
        for chat in unread_group_chats:
            print(f"Group Chat: {chat['chat_name']}, Unread messages: {chat['unread_count']}")

        # Extract only channels
        unread_channel_chats = get_unread_chats(client, include_private=False, include_groups=False, include_channels=True)
        print("\nUnread channels:")
        for chat in unread_channel_chats:
            print(f"Channel: {chat['chat_name']}, Unread messages: {chat['unread_count']}")

        # Extract all types of chats, including muted ones
        unread_all_chats = get_unread_chats(client, include_private=True, include_groups=True, include_channels=True, include_muted=True)
        print("\nUnread private chats, group chats, and channels (including muted):")
        for chat in unread_all_chats:
            print(f"Chat: {chat['chat_name']}, Unread messages: {chat['unread_count']}")
            for message in chat['unread_messages']:
                print(f"  - {message}")