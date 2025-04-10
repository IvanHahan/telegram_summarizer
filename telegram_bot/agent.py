import uuid
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Literal, TypedDict

from .nodes import (
    chat_node,
    route_llm_request,
    route_user_request,
    summarize_node,
    unread_messages_node,
)


# --- State Definition ---
class State(TypedDict):
    action: Literal["message", "unread_summary"]
    messages: Annotated[list, add_messages]
    unread_chats: list
    

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
        ["unread_messages_node", "summarize_node", END],
    )

    workflow.add_edge("unread_messages_node", "summarize_node")
    workflow.add_edge("summarize_node", END)

    return workflow.compile()


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
