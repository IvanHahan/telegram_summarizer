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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
workflow = create_workflow()


async def what_i_missed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """what i missed request"""
    res = await workflow.ainvoke(
        {'action': 'unread_summary'}, config=config
    )
    await update.message.reply_text(res['messages'][-1].content)


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
    res = await workflow.ainvoke(
        {'action': 'message', 'messages': [update.message.text]}, config=config
    )
    await update.message.reply_text(
        res['messages'][-1].content
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freeform_message))  # Freeform handler

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()