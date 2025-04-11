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

from telegram_bot.persistance import clear_user_state, get_user_state, save_user_state
from telegram_bot.redis_saver import AsyncRedisSaver
from telegram_bot.telegram_utils import create_telegram_client, mark_chats_as_read
from telegram_bot.workflow import create_workflow

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
memory = AsyncRedisSaver.from_conn_info(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=os.getenv("REDIS_PORT", 6379),
    db=0,
)
from langgraph.checkpoint.memory import MemorySaver

workflow = create_workflow(MemorySaver())

async def chat_with_bot(user_id, message):
    # state = await get_user_state(user_id)  # Retrieve state from Redis
    # state['action'] = 'message'
    # if not state.get('messages'):
    #     state['messages'] = []
    # state['messages'].append(HumanMessage(message))
    state = await workflow.ainvoke(
        {'messages': [HumanMessage(message)], 'user_id': str(user_id)}, config={'thread_id': user_id}
    )
    # await save_user_state(user_id, state)  # Save updated state to Redis
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

    # Send the response to the user
    await update.message.reply_text(res['messages'][-1].content)

    # If there are unread chats, prompt the user to mark them as read
    if res['unread_chats']:
        await create_mark_as_read_handler(update)

    await save_user_state(user_id, state)  # Save updated state to Redis

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
    # Clear Redis cache for the user
    user_id = update.effective_user.id
    clear_user_state(user_id)
    await update.effective_message.reply_text("All clear!")

    

async def handle_freeform_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles freeform text messages from users."""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    try:
        # Process the message through the bot
        state = await chat_with_bot(user_id, user_message)
        
        # Handle bot response
        await send_bot_response(update, state)
        
        # Handle any follow-up actions from the state
        await process_follow_up_actions(update, state)
        
        # Save the final state
        await save_user_state(user_id, state)
        
    except Exception as e:
        logger.error(f"Error processing message from user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Sorry, I encountered an error while processing your message."
        )


async def send_bot_response(update: Update, state: dict) -> None:
    """Sends the bot's response message to the user if available."""
    # Safety check for messages array
    if not state.get('messages'):
        return
    
    try:
        # Get the last message if it's an AI response
        last_message = state['messages'][-1]
        if isinstance(last_message, AIMessage) and hasattr(last_message, 'content'):
            # Send the AI's response
            await update.message.reply_text(last_message.content)
    except IndexError:
        logger.warning("Attempted to access last message but messages list was empty")
    except Exception as e:
        logger.error(f"Error sending bot response: {str(e)}")


async def process_follow_up_actions(update: Update, state: dict) -> None:
    """Process any follow-up actions based on the current state."""
    # Handle unread chats
    if state.get('unread_chats') and len(state['unread_chats']) > 0:
        # Add a message about marking as read to the conversation
        if 'messages' in state:
            state['messages'].append(AIMessage("Would you like to mark them as read?"))
        await create_mark_as_read_handler(update)
    
    # Handle chat selection
    if state.get('chats_to_select') and len(state['chats_to_select']) > 0:
        # Add a message about selecting a chat to the conversation
        if 'messages' in state:
            state['messages'].append(AIMessage("Please select a chat to send a message to."))
        
        # Create keyboard with chats
        keyboard = [
            [InlineKeyboardButton(chat['chat_name'], 
                                 callback_data=f"select_chat:{chat['chat_id']}")]
            for chat in state['chats_to_select']
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a chat to send a message to:",
            reply_markup=reply_markup
        )


async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Mark as Read' button."""
    user_id = update.effective_user.id
    state = await get_user_state(user_id)  # Retrieve state from Redis
    unread_chats = state.get('unread_chats', [])

    # Mark chats as read
    async with create_telegram_client() as client:
        chat_ids = [chat['chat_id'] for chat in unread_chats]
        await mark_chats_as_read(client, chat_ids)

    state['messages'].append(AIMessage("Done! All unread messages have been marked as read."))
    await update.effective_message.edit_text(state['messages'][-1].content)
    await save_user_state(user_id, state)  # Save updated state to Redis


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

    application.add_handler(CommandHandler("what_i_missed", what_i_missed))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
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