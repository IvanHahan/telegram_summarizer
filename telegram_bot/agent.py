import os
import uuid
from typing import Annotated

from langchain_core.messages import SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from telegram_bot.telegram import create_telegram_client, get_unread_chats

system_message = """
    You are a messenger assistant. Your task is to analyze messages and provide some insights about them.
"""

summarize_prompt = PromptTemplate(
    input_variables=["messages"],
    template="""
    You are a chat summarization assistant. Your task is to summarize the following unread chats or messages:
    {messages}
    Please provide a concise summary of the messages per chat if provided, highlighting the main points and any important details including authors. You must answer in Ukranian language.
    """
)

def get_messages_info(messages):
    return [SystemMessage(content=system_message)] + messages


def format_chats(chats):
    formatted_chats = []
    for chat in chats:
        chat_name = chat["chat_name"]
        unread_messages = chat["unread_messages"]
        formatted_messages = [
            f"{msg['sender_name']}: {msg['text']}" for msg in unread_messages
        ]
        formatted_chats.append(f"Chat: {chat_name}\n" + "\n".join(formatted_messages))
    return "\n\n".join(formatted_chats)


llm = ChatOpenAI(
        base_url="https://api.together.xyz/v1",
        api_key=os.environ["TOGETHER_API_KEY"],
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    )

class State(TypedDict):
    messages: Annotated[list, add_messages]
    unread_messages_summary: str
    unread_chats: list


def unread_messages_node(state):
    with create_telegram_client() as client:
        unread_chats = get_unread_chats(client, max_unread_count=5)
    return {"unread_chats": unread_chats}

def summarize_node(state):
    chain = summarize_prompt | llm
    response = chain.invoke(input={'messages': state['unread_chats']})
    return {"messages": [response]}


memory = MemorySaver()
workflow = StateGraph(State)
workflow.add_node("summarize", summarize_node)
workflow.add_node("extract_unread_messages", unread_messages_node)

workflow.add_edge(START, "extract_unread_messages")
workflow.add_edge("extract_unread_messages", "summarize")
workflow.add_edge("summarize", END)
graph = workflow.compile(checkpointer=memory)
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
res = graph.invoke(
    {
        "messages": ['hello']
    }, config=config
)

print(res)
