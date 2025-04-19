import os

from langchain_openai import ChatOpenAI


def create_llm():
    return ChatOpenAI(model_name="gpt-4-turbo")
    return ChatOpenAI(model_name="gpt-3.5-turbo")
    return ChatOpenAI(
        base_url="https://api.together.xyz/v1",
        api_key=os.environ["TOGETHER_API_KEY"],
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    )


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
            f"{msg['sender_name']}: {msg['text']}" if 'sender_name' in msg else msg['text'] for msg in messages if msg['text']
        ]
        title = 'Chat'
        if chat["is_channel"]:
            title = 'Channel'
        elif chat["is_group"]:
            title = 'Group'
        formatted_chats.append(f"{title}: {chat_name}\n" + f"Chat ID: {chat['chat_id']}\n" + "\n".join(formatted_messages))
    return "\n\n".join(formatted_chats)


def format_messages(messages):
    return [
            f"{msg['sender_name']}: {msg['text']}" if 'sender_name' in msg else msg['text'] for msg in messages if msg['text']
        ]