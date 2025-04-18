# --- Constants ---
SYSTEM_MESSAGE = """
    You are a messenger assistant.
    Your task is to summarize unread history, analyze messages and provide some insights about them.
    You may be asked to provide summary, example replies, answer messages or analyze message history.
"""

SUMMARIZE_PROMPT_TEMPLATE = """
    Summarize messages in given chats in several sentences for every chat.
    Include the most important information and key points.
    Answer in the language of the user's messages.
    
    the chats are: {chats}
"""

ANALYZE_CHAT_PROMPT_TEMPLATE = """
    Analyze the given chat and provide insights about it.
    Analyze sentiment, engagement, and any other relevant metrics.
    Provide a summary of the chat's activity and any notable trends.
    Answer in the language of the user's messages.
    the chat is: {chat}
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