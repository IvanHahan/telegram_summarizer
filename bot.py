#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""This example showcases how PTBs "arbitrary callback data" feature can be used.

For detailed info on arbitrary callback data, see the wiki page at
https://github.com/python-telegram-bot/python-telegram-bot/wiki/Arbitrary-callback_data

Note:
To use arbitrary callback data, you must install PTB via
`pip install "python-telegram-bot[callback-data]"`
"""
import json
import logging
import os
import uuid

import redis
from langchain_core.messages import AIMessage, HumanMessage
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InvalidCallbackData,
    MessageHandler,
    PicklePersistence,
    filters,
)

from telegram_bot.agent import create_workflow
from telegram_bot.telegram_utils import create_telegram_client, mark_chats_as_read

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
workflow = create_workflow()

# Initialize Redis client
redis_client = redis.StrictRedis(host="localhost", port=6379, db=0, decode_responses=True)

async def save_user_state(user_id: int, state: dict) -> None:
    """Save user state to Redis."""
    state['messages'] = [msg.to_json() for msg in state['messages']]
    redis_client.set(f"user:{user_id}:state", json.dumps(state))

def message_decoder(data):
    if isinstance(data, dict) and "id" in data and "kwargs" in data:
        class_id = data["id"]
        kwargs = data["kwargs"]
        if class_id[-1] == "HumanMessage":
            return HumanMessage(**kwargs)
        elif class_id[-1] == "AIMessage":
            return AIMessage(**kwargs)
    return data

async def get_user_state(user_id: int) -> dict:
    """Retrieve user state from Redis."""
    state = redis_client.get(f"user:{user_id}:state")
    state = json.loads(state) if state else {}
    if state.get('messages'):
        state['messages'] = [message_decoder(msg) for msg in state['messages']] 
    return state


async def create_mark_as_read_handler(update: Update):
    keyboard = [
            [
                InlineKeyboardButton("Mark as Read", callback_data="mark_as_read"),
                InlineKeyboardButton("Cancel", callback_data="no_action")
            ]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Would you like to mark unread as read?",
        reply_markup=reply_markup
    )


async def what_i_missed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'What I Missed' request."""
    user_id = update.effective_user.id
    state = await get_user_state(user_id)  # Retrieve state from Redis
    state['action'] = 'unread_summary'
    
    # Invoke the workflow and save the result
    res = await workflow.ainvoke(state, config=config)
    state['messages'] = res['messages']
    state['unread_chats'] = res.get('unread_chats', [])
    await save_user_state(user_id, state)  # Save updated state to Redis

    # Send the response to the user
    await update.message.reply_text(res['messages'][-1].content)

    # If there are unread chats, prompt the user to mark them as read
    if res['unread_chats']:
        await create_mark_as_read_handler(update)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    keyboard = [
        [InlineKeyboardButton("What I Missed", callback_data="what_i_missed")],
        [InlineKeyboardButton("Help", callback_data="help")],
        [InlineKeyboardButton("Clear", callback_data="clear")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to the Telegram Summarizer Bot! Use the buttons below to get started:",
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays info on how to use the bot."""
    await update.message.reply_text(
        "Use /start to test this bot. Use /clear to clear the stored data so that you can see "
        "what happens, if the button data is not available. "
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the callback data cache"""
    context.bot.callback_data_cache.clear_callback_data()
    context.bot.callback_data_cache.clear_callback_queries()
    await update.effective_message.reply_text("All clear!")


async def handle_invalid_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Informs the user that the button is no longer available."""
    await update.callback_query.answer()
    await update.effective_message.edit_text(
        "Sorry, I could not process this button click 😕 Please send /start to get a new keyboard."
    )


async def handle_freeform_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles freeform text messages."""

    user_id = update.effective_user.id
    state = await get_user_state(user_id)  # Retrieve state from Redis
    state['action'] = 'message'
    if not state.get('messages'):
        state['messages'] = []
    state['messages'].append(HumanMessage(update.message.text))

    res = await workflow.ainvoke(
        state, config=config
    )
    context.user_data['state'] = res
    await update.message.reply_text(
        res['messages'][-1].content
    )
    await save_user_state(user_id, state)  # Save updated state to Redis
    
    if 'unread_chats' in res and len(res['unread_chats']) > 0:
        state['messages'].append(AIMessage("Would you like to mark them as read?"))
        await create_mark_as_read_handler(update)
    



async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Mark as Read' button."""
    user_id = update.effective_user.id
    state = await get_user_state(user_id)  # Retrieve state from Redis
    unread_chats = state.get('unread_chats', [])

    # Mark chats as read
    async with create_telegram_client() as client:
        chat_ids = [chat['chat_id'] for chat in unread_chats]
        await mark_chats_as_read(client, chat_ids)

    state['unread_chats'] = []  # Clear unread chats after marking as read
    state['messages'].append(AIMessage("Done! All unread messages have been marked as read."))
    await save_user_state(user_id, state)  # Save updated state to Redis
    await update.effective_message.edit_text(state['messages'][-1].content)


async def no_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Cancel' button."""
    await update.callback_query.answer()  # Acknowledge the callback query
    state = context.user_data.get('state', {})
    state['messages'].append(HumanMessage("Cancel"))
    state['messages'].append(AIMessage("Ok"))
    state['unread_chats'] = []  # Clear unread chats
    await update.effective_message.edit_text(
        "No action was taken."
    )


def main() -> None:
    """Run the bot."""
    persistence = PicklePersistence(filepath="arbitrarycallbackdatabot")
    application = (
        Application.builder()
        .token(os.getenv("TELEGRAM_TOKEN"))
        .persistence(persistence)
        .arbitrary_callback_data(True)
        .build()
    )

    application.add_handler(CommandHandler("what_i_missed", what_i_missed))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(
        CallbackQueryHandler(handle_invalid_button, pattern=InvalidCallbackData)
    )
    application.add_handler(
        CallbackQueryHandler(mark_as_read, pattern="mark_as_read")
    )  # Add the new handler here
    application.add_handler(
        CallbackQueryHandler(no_action, pattern="no_action")
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freeform_message))  # Freeform handler

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()