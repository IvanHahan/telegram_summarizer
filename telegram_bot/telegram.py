import os

from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")
phone_number = os.getenv("PHONE_NUMBER")

def get_unread_chats(client, 
                     include_private=True, 
                     include_groups=False, 
                     include_channels=False, 
                     include_muted=False, 
                     max_unread_count=None):
    """
    Extract unread messages from private chats, group chats, and/or channels based on the provided flags.
    
    Args:
        client (TelegramClient): An instance of the TelegramClient.
        include_private (bool): Whether to include private chats in the results.
        include_groups (bool): Whether to include group chats in the results.
        include_channels (bool): Whether to include channels in the results.
        include_muted (bool): Whether to include muted chats and channels in the results.
        max_unread_count (int, optional): Maximum number of unread messages to extract per chat. If None, all unread messages are extracted.
    
    Returns:
        list: A list of dictionaries containing chat names, unread message counts, and unread messages.
    """
    unread_chats = []
    dialogs = client.get_dialogs()
    for dialog in dialogs:
        if dialog.unread_count > 0:  # Check if the chat has unread messages
            # Check if the chat is muted
            is_muted = dialog.dialog.notify_settings and dialog.dialog.notify_settings.mute_until
            if not include_muted and is_muted and is_muted:
                continue
            
            if (include_private and dialog.is_user) or \
               (include_groups and dialog.is_group) or \
               (include_channels and dialog.is_channel):
                # Fetch unread messages
                unread_messages = []
                for message in client.iter_messages(dialog.id, limit=max_unread_count):
                    sender_name = None
                    if message.sender:
                        sender_name = message.sender.first_name or message.sender.last_name or message.sender.username
                    unread_messages.append({
                        "text": message.text,
                        "sender_id": message.sender_id,
                        "sender_name": sender_name
                    })
                
                unread_chats.append({
                    "chat_name": dialog.name,
                    "unread_count": dialog.unread_count,
                    "unread_messages": unread_messages
                })
    return unread_chats

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
    
    client = TelegramClient(session_name, api_id, api_hash)
    return client

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