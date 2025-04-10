# --- Constants ---
SYSTEM_MESSAGE = """
    You are a messenger assistant. Your task is to analyze messages and provide some insights about them.
    You must answer in Ukrainian language.
"""

SUMMARIZE_PROMPT_TEMPLATE = """
    Summarize messages in given chats in several sentences for every chat. Use the following format:
    
    Chats:
    <Chat name 1>: <summary_for_chat>
    <Chat name 2>: <summary_for_chat>

    Channels:
    <Channel_name_1>: summary_for_channel
    <Channel_name_2>: summary_for_channel

    Groups:
    <Group_name_1>: summary_for_group
    <Group_name_2>: summary_for_group

"""