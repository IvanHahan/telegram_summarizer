import uuid

from telegram_bot.rigid_workflow import create_workflow


# --- Main Execution ---
async def main():
    """
    Main entry point for the script.
    """
    workflow = create_workflow()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    # res = await workflow.ainvoke({"messages": ["Що я пропустив?"], "action": "message"}, config=config)
    # res = await workflow.ainvoke({"messages": ["Дай мені чат з Наталей"], "action": "message"}, config=config)
    res = await workflow.ainvoke({"messages": ["Hапиши Принцесе, шо я не хочу морозиво"], "action": "message"}, config=config)
    # res = await workflow.ainvoke({"messages": ["what's your name?"], "action": "message"}, config=config)
    print(res)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    # asyncio.run(agent.ainvoke({'messages': [HumanMessage('what I missed?')]})

