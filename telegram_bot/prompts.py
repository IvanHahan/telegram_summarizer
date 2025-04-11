# --- Constants ---
SYSTEM_MESSAGE = """
    You are a messenger assistant. 
    Your task is to analyze messages and provide some insights about them.
    You may be asked to provide summary, example replies, answer messages or analyze message history.
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
    
    the chats are: {chats}
"""


ReAct_PROMPT_TEMPLATE = """
{instructions}

TOOLS:
------

You have access to the following tools:

{tools}

To use a tool, please use the following format:

```
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
```

When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:

```
Thought: Do I need to use a tool? No
Final Answer: [your response here]
```

Begin!

"""