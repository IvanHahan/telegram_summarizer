import logging
import os
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.redis import AsyncRedisSaver
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from login_handler import (
    authorize,
    cancel,
    receive_code,
    receive_contact,
    receive_password,
    resend_code,
)
from telegram_bot.store import create_store
from telegram_bot.telegram_utils import is_authorized
from telegram_bot.workflow import create_workflow

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
store = create_store('async_redis')


# Conversation states
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)

# Obfuscation constant
OBFUSCATION_CONSTANT = 1000

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome! Use /authorize to log in with your phone number or /info to see user info."
    )

async def recieve_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages from the user."""
    await run_bot(update, context)

async def run_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = None, action: str = 'message') -> None:
    user_id = update.effective_user.id
    if await is_authorized(f"session_{user_id}"):
        async with AsyncRedisSaver(f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', 6379)}/0") as checkpointer:
            if not 'thread_id' in context.user_data:
                context.user_data['thread_id'] = uuid.uuid4().hex
            session_id = context.user_data.get('thread_id')
            workflow = create_workflow(checkpointer)
            user_message = update.message.text
            if message:
                user_message = message
            # try:
                # Process the message through the bot
            state = await workflow.ainvoke(
            {'messages': [HumanMessage(user_message)], 'action': action}, config={'thread_id': session_id}
            )
            try:
                # Handle bot response
                await send_bot_response(update, state)
                
                # Handle any follow-up actions from the state
                await process_follow_up_actions(update, state)

                thread_id = context.user_data.get('thread_id')
                keys = await checkpointer._redis.keys(f"checkpoint${thread_id}*")
                for key in keys:
                    await checkpointer._redis.setex(key, 1800)
                
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}: {str(e)}")
                await update.message.reply_text(
                    "Sorry, I encountered an error while processing your message."
                )

    else:
        await authorize(update, context)


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
        await mark_as_read_handler(update)
    
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

async def mark_as_read_handler(update: Update):
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

def main() -> None:
    """Run the bot."""
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("authorize", authorize)],
        states={
            SHARE_CONTACT: [MessageHandler(filters.CONTACT, receive_contact)],
            ENTER_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code),
                CommandHandler("resend", resend_code),
            ],
            ENTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recieve_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()