import os
from pathlib import Path

from pyrogram import Client, filters

from src.machines.auth_machine import AuthorizationMachine

user_clients = {}


async def get_user_client(user_id: int) -> Client:
    if user_id not in user_clients:
        session_file = Path(f"{user_id}")
        client = Client(
            str(session_file),
            api_id=os.getenv("TELEGRAM_API_ID"),
            api_hash=os.getenv("TELEGRAM_API_HASH"),
        )
        await client.connect()
        user_clients[user_id] = client
    return user_clients[user_id]


bot = Client(
    "assistant",
    api_id=int(os.getenv("TELEGRAM_API_ID")),
    api_hash=os.getenv("TELEGRAM_API_HASH"),
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
)


@bot.on_message(filters.command("ping"))
async def start(client: Client, message):
    await client.send_message(message.chat.id, "Pong!")


@bot.on_message(filters.command("summarize"))
async def summarize(client: Client, message):
    # Get chat history from the last read message
    chat_id = message.chat.id
    unread_messages = []
    async with Client(str(message.from_user.id)) as user_client:
        if not await user_client.get_me():
            await client.send_message(
                message.chat.id,
                "You need to authorize first. Use /authorize command.",
            )
            return
        # Get recent messages (you may need to adjust the limit based on your needs)
        async for msg in user_client.get_chat_history(chat_id, limit=100):
            # Stop when we reach the message that triggered the command
            if msg.id == message.id:
                break
            unread_messages.append(msg)

    # Reverse to get chronological order
    unread_messages.reverse()
    await client.send_message(message.chat.id, "Summarizing...")


@bot.on_message(filters.command("authorize"))
async def authorize(client: Client, message):
    user_id = message.from_user.id
    user_client = await get_user_client(user_id)
    if await user_client.get_me():
        await message.reply("You are already authorized.")
        return
    auth = AuthorizationMachine()
    await auth.start_auth(
        client=client, message=message
    ) or await auth.handle_authorized(client=client, message=message)


if __name__ == "__main__":
    bot.run()
