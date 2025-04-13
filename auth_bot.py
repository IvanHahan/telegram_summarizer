import logging
import os
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.redis import AsyncRedisSaver
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from telegram_bot.store import create_store
from telegram_bot.telegram_utils import create_telegram_client, is_authorized
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

async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the authorization process by requesting contact sharing."""
    contact_button = KeyboardButton("Share Contact", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Please share your contact to authorize. This will provide your phone number securely.",
        reply_markup=reply_markup
    )
    return SHARE_CONTACT

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the shared contact and initiate authorization."""
    user_id = update.effective_user.id
    contact = update.message.contact
    
    if not contact:
        await update.message.reply_text("No contact received. Please try /authorize again.")
        return ConversationHandler.END

    phone_number = contact.phone_number
    if not phone_number.startswith('+'):
        phone_number = f"+{phone_number}"
    context.user_data['phone_number'] = phone_number
    context.user_data['session_name'] = f"session_{user_id}"  # Unique session per user

    try:
        client = create_telegram_client(context.user_data['session_name'])
        context.user_data['client'] = client
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            await update.message.reply_text(
                f"Contact received! Telegram sent a code to {phone_number}. To send it securely, "
                f"add {OBFUSCATION_CONSTANT} to the code (e.g., if the code is 12345, send {12345 + OBFUSCATION_CONSTANT}). "
                "Enter the modified code within 2 minutes. Use /resend if it expires.",
                reply_markup=ReplyKeyboardMarkup([])  # Clear keyboard
            )
            return ENTER_CODE
        else:
            await update.message.reply_text("Already authorized!")
            await client.disconnect()
            return ConversationHandler.END
    except PhoneNumberInvalidError:
        await update.message.reply_text("Invalid phone number. Please try /authorize again.")
        return ConversationHandler.END
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try /authorize again.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Authorization initiation error: {e}")
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the obfuscated code input."""
    user_id = update.effective_user.id
    if 'client' not in context.user_data or 'phone_number' not in context.user_data:
        await update.message.reply_text("No active authorization session. Please start with /authorize.")
        return ConversationHandler.END

    client = context.user_data['client']
    phone_number = context.user_data['phone_number']
    
    try:
        obfuscated_code = update.message.text.strip()
        try:
            obfuscated_code = int(obfuscated_code)
            real_code = str(obfuscated_code - OBFUSCATION_CONSTANT)  # Decode the code
        except ValueError:
            await update.message.reply_text("Please send a numeric code. Add {OBFUSCATION_CONSTANT} to the Telegram code and try again.")
            return ENTER_CODE

        await client.sign_in(phone_number, real_code)
        await update.message.reply_text("Authorization successful!")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END
    except PhoneCodeExpiredError:
        await update.message.reply_text(
            "The code has expired. Use /resend to get a new code or /cancel to stop."
        )
        return ENTER_CODE
    except SessionPasswordNeededError:
        await update.message.reply_text("Two-factor authentication enabled. Please enter your password:")
        return ENTER_PASSWORD
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try again.")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Code sign-in error: {e}")
        await update.message.reply_text(
            f"Invalid code or error: {e}. Ensure you added {OBFUSCATION_CONSTANT} to the Telegram code. "
            "Use /resend for a new code or /cancel to stop."
        )
        return ENTER_CODE

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the 2FA password input."""
    client = context.user_data.get('client')
    if not client:
        await update.message.reply_text("No active authorization session. Please start with /authorize.")
        return ConversationHandler.END

    password = update.message.text.strip()
    
    try:
        await client.sign_in(password=password)
        await update.message.reply_text("Authorization successful!")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try again.")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Password sign-in error: {e}")
        await update.message.reply_text(f"Invalid password or error: {e}. Try /authorize again.")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END

async def resend_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Resend the authorization code."""
    client = context.user_data.get('client')
    phone_number = context.user_data.get('phone_number')
    
    if not client or not phone_number:
        await update.message.reply_text("No active authorization session. Please start with /authorize.")
        return ConversationHandler.END
    
    try:
        await client.send_code_request(phone_number, force_sms=False)
        await update.message.reply_text(
            f"A new code was sent to {phone_number}. Add {OBFUSCATION_CONSTANT} to it (e.g., 12345 becomes {12345 + OBFUSCATION_CONSTANT}) "
            "and enter the modified code within 2 minutes."
        )
        return ENTER_CODE
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try again.")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Resend code error: {e}")
        await update.message.reply_text(f"Error resending code: {e}. Try /authorize again.")
        await client.disconnect()
        context.user_data.clear()
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the authorization process."""
    client = context.user_data.get('client')
    if client:
        await client.disconnect()
    context.user_data.clear()
    await update.message.reply_text("Authorization cancelled.")
    return ConversationHandler.END


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