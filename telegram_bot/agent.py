import os
import uuid
from typing import Annotated

from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

from telegram_bot.telegram import create_telegram_client, get_unread_chats

# --- Constants ---
SYSTEM_MESSAGE = """
    You are a messenger assistant. Your task is to analyze messages and provide some insights about them.
"""

SUMMARIZE_PROMPT_TEMPLATE = """
    You are a chat summarization assistant. Your task is to summarize the following unread chats or messages:
    {messages}
    Please provide a concise summary of the messages per chat if provided, highlighting the main points and any important details including authors. You must answer in Ukranian language.
"""


# --- Prompt and LLM Setup ---
def create_summarize_prompt():
    return PromptTemplate(
        input_variables=["messages"],
        template=SUMMARIZE_PROMPT_TEMPLATE,
    )


def create_llm():
    return ChatOpenAI(model_name="gpt-3.5-turbo")
    return ChatOpenAI(
        base_url="https://api.together.xyz/v1",
        api_key=os.environ["TOGETHER_API_KEY"],
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    )

@tool
async def get_unread_chats_tool() -> list:
    """
    Fetch unread chats from Telegram, including groups. Call only if the user requests it.
    """
    async with create_telegram_client() as client:
        unread_chats = await get_unread_chats(client, include_groups=True)
    return unread_chats

llm = create_llm()
llm_with_tools = llm.bind_tools([get_unread_chats_tool])

# --- Formatting Functions ---
def format_chats(chats):
    """
    Format unread chats into a human-readable string.
    """
    formatted_chats = []
    for chat in chats:
        chat_name = chat["chat_name"]
        unread_messages = chat["unread_messages"]
        formatted_messages = [
            f"{msg['sender_name']}: {msg['text']}" for msg in unread_messages
        ]
        formatted_chats.append(f"Chat: {chat_name}\n" + "\n".join(formatted_messages))
    return "\n\n".join(formatted_chats)


# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary"]
    messages: Annotated[list, add_messages]


def route_user_request(state):
    if state['action'] == 'unread_summary':
        return "unread_messages_node"
    elif state['action'] == 'message':
        return "chat_node"
        

def chat_node(state):
    messages = state['messages']
    messages = [SystemMessage(SYSTEM_MESSAGE)] + messages
    response = llm_with_tools.invoke(input=messages)
    state["messages"] += [response]
    return state


def route_llm_request(state):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if last_message.tool_calls[0]['name'] == "get_unread_chats_tool":
            return "unread_messages_node"
        return END
    else:
        return END


# --- Workflow Nodes ---
async def unread_messages_node(state):
    """
    Extract unread messages from Telegram chats.
    """
    unread_chats = await get_unread_chats_tool.ainvoke({})
    state['messages'][-1] = AIMessage(format_chats(unread_chats))
    return state


def summarize_node(state):
    """
    Summarize unread messages using the LLM.
    """
    summarize_prompt = f"provide a summary for the given chats in Ukrainian language"
    messages = [SystemMessage(SYSTEM_MESSAGE)] + state['messages'] + [HumanMessage(summarize_prompt)]
    response = llm.invoke(input=messages)
    state['messages'] += [response]
    return state


# --- Workflow Setup ---
def create_workflow():
    """
    Create and compile the workflow for processing unread messages and summarizing them.
    """
    memory = MemorySaver()
    workflow = StateGraph(State)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("unread_messages_node", unread_messages_node)
    workflow.add_node("summarize_node", summarize_node)

    workflow.add_conditional_edges(START, 
                                   route_user_request, ["chat_node", "unread_messages_node"])

    workflow.add_conditional_edges(
        "chat_node",
        route_llm_request,
        ["unread_messages_node", END],
    )

    workflow.add_edge("unread_messages_node", "summarize_node")
    workflow.add_edge("summarize_node", END)

    return workflow.compile(checkpointer=memory)


# --- Main Execution ---
async def main():
    """
    Main entry point for the script.
    """
    workflow = create_workflow()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    res = await workflow.ainvoke({"messages": ["Що я пропустив?"], "action": "message"}, config=config)
    # res = await workflow.ainvoke({"messages": ["what's your name?"], "action": "message"}, config=config)
    print(res)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
