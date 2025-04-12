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
import logging
import os
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    filters,
)
from telethon.errors import PhoneCodeExpiredError

from telegram_bot.bot_utils import authorization_handler, bot_handler
from telegram_bot.store import create_store
from telegram_bot.telegram_utils import create_telegram_client, is_authorized

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

store = create_store('async_redis')


async def get_thread_id(user_id):
    thread_id = await store.get(f"thread_id:{user_id}")
    if thread_id is None:
        thread_id = uuid.uuid4().hex
    await store.set(f"thread_id:{user_id}", thread_id, expire=1800)
    return thread_id

async def set_thread_id(user_id, thread_id):
    await store.set(f"thread_id:{user_id}", thread_id, expire=1800)

async def reset_thread_id(user_id):
    await store.delete(f"thread_id:{user_id}")

async def set_expire_for_user(user_id):
    thread_id = await get_thread_id(user_id)
    keys = await store.redis_client.keys(f"checkpoint${thread_id}*")
    for key in keys:
        await store.redis_client.setex(key, 1800)

async def clear_for_user(user_id):
    await store.delete(f"auth:{user_id}")
    thread_id = await get_thread_id(user_id)
    keys = await store.redis_client.keys(f"checkpoint${thread_id}*")
    for key in keys:
        await store.delete(key)


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact is not None:
        phone = contact.phone_number
        user_id = contact.user_id
        await update.message.reply_text(f"Thanks! Your number is {phone}")
        if not await is_authorized(user_id):
            client = create_telegram_client(user_id)
            await client.connect()
            res = await client.send_code_request(phone)
            await store.set_object(f"auth:{user_id}", {'phone': phone, 'phone_code_hash': res.phone_code_hash})
            await update.message.reply_text("Please enter the code sent to your phone:")

async def handle_code(update: Update, auth: dict):
    code = update.message.text
    user_id = update.effective_user.id
    client = create_telegram_client(user_id)
    await client.connect()
    try:
        auth['code'] = code
        await client.sign_in(**auth)
        await store.delete(f"auth:{user_id}")
        await update.message.reply_text("You are now authorized!")
    except PhoneCodeExpiredError:
        await update.message.reply_text("The code has expired. Please try again.")
        await clear_for_user(user_id)
    except Exception as e:
        logger.error(f"Error during sign-in: {str(e)}")
        await update.message.reply_text("Failed to authorize. Please try again.")


async def what_i_missed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'What I Missed' request."""

    await bot_handler(update, action='missed')

async def analyze_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'What I Missed' request."""

    await bot_handler(update, action='analyze', session_id=get_thread_id(update.effective_user.id))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command.""" 
    if not authorization_handler(update):
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
    # Clear Redis cache for the user
    user_id = update.effective_user.id
    await clear_for_user(user_id)
    await update.effective_message.reply_text("All clear!")
    

async def handle_freeform_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles freeform text messages from users."""

    auth = await store.get_object(f"auth:{update.effective_user.id}")
    if auth:
        await handle_code(update, auth)
    else:
        await bot_handler(update, 
                          session_id=await get_thread_id(update.effective_user.id),
                          action='message')
        await set_expire_for_user(update.effective_user.id)

async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Mark as Read' button."""
    await bot_handler(update, action='mark_as_read')


async def no_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Cancel' button."""
    await update.callback_query.answer()  # Acknowledge the callback query
    state = context.user_data.get('state', {})
    state['messages'].append(HumanMessage("Cancel"))
    state['messages'].append(AIMessage("Ok"))
    await update.effective_message.edit_text(
        "No action was taken."
    )


async def select_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the selection of a chat from the 'chats_to_select' buttons."""
    user_id = update.effective_user.id
    state = await get_user_state(user_id)  # Retrieve state from Redis

    # Extract the selected chat ID from the callback data
    callback_data = update.callback_query.data
    selected_chat_id = callback_data.split(":")[1]  # Extract chat ID from "select_chat:<chat_id>"

    # Find the selected chat in the state
    selected_chat = next(
        (chat for chat in state.get('chats_to_select', []) if str(chat['chat_id']) == selected_chat_id),
        None
    )
    state['chats_to_select'] = []
    

    if selected_chat:
        # Save the selected chat in the state
        # state['messages'].append(HumanMessage(f"Chat ID: '{selected_chat['chat_name']}' selected."))
        state = await chat_with_bot(user_id, f"Chat '{selected_chat['chat_name']}' with ID: {selected_chat['chat_id']} selected.")
        await update.callback_query.answer()
        await update.effective_message.edit_text(
            state['messages'][-1].content
        )

        # Notify the user
        
    else:
        # Handle the case where the chat is not found
        await update.callback_query.answer("Chat not found.", show_alert=True)
    
    await save_user_state(user_id, state)  # Save updated state to Redis


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

    application.add_handler(CommandHandler("missed", what_i_missed))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("analyze", analyze_chat))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(
        CallbackQueryHandler(mark_as_read, pattern="mark_as_read")
    )  # Add the new handler here
    application.add_handler(
        CallbackQueryHandler(no_action, pattern="no_action")
    )
    application.add_handler(
        CallbackQueryHandler(select_chat, pattern="select_chat:")
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freeform_message))  # Freeform handler

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()