# --- Formatting Functions ---
def format_chats(chats):
    """
    Format unread chats into a human-readable string.
    """
    formatted_chats = []
    for chat in chats:
        chat_name = chat["chat_name"]
        messages = chat["messages"]
        formatted_messages = [
            (
                f"{msg['sender_name']}: {msg['text']}"
                if "sender_name" in msg
                else msg["text"]
            )
            for msg in messages
            if msg["text"]
        ]
        title = "Chat"
        if chat["is_channel"]:
            title = "Channel"
        elif chat["is_group"]:
            title = "Group"
        formatted_chats.append(
            f"{title}: {chat_name}\n"
            + f"Chat ID: {chat['chat_id']}\n"
            + "\n".join(formatted_messages)
        )
    return "\n\n".join(formatted_chats)


def format_messages(messages):
    return "\n".join(
        [
            (
                f"{msg['sender_name']}: {msg['text']}"
                if "sender_name" in msg
                else msg["text"]
            )
            for msg in messages
            if msg["text"]
        ]
    )
