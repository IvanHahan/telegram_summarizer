import logging

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from telegram_bot.telegram_utils import create_telegram_client, is_authorized

logger = logging.getLogger(__name__)

# Conversation states
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)

# Constants
OBFUSCATION_CONSTANT = 1000
SESSION_PREFIX = "session_"
AUTH_ERROR_MSG = "No active authorization session. Please start with /authorize."


async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the authorization process by requesting contact sharing."""
    user_id = update.effective_user.id
    session_name = f"{SESSION_PREFIX}{user_id}"
    
    if await is_authorized(session_name):
        await update.message.reply_text("You are already authorized!")
        return ConversationHandler.END
        
    contact_button = KeyboardButton("Share Contact", request_contact=True)
    reply_markup = ReplyKeyboardMarkup(
        [[contact_button]], one_time_keyboard=True, resize_keyboard=True
    )
    
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

    # Process phone number
    phone_number = contact.phone_number
    if not phone_number.startswith('+'):
        phone_number = f"+{phone_number}"
        
    # Store data in context
    session_name = f"{SESSION_PREFIX}{user_id}"
    context.user_data['phone_number'] = phone_number
    context.user_data['session_name'] = session_name

    try:
        # Create and connect the client
        client = create_telegram_client(session_name)
        context.user_data['client'] = client
        await client.connect()
        
        # Check authorization status and send code if needed
        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            await update.message.reply_text(
                f"Contact received! Telegram sent a code to {phone_number}. "
                f"To send it securely, add {OBFUSCATION_CONSTANT} to the code "
                f"(e.g., if the code is 12345, send {12345 + OBFUSCATION_CONSTANT}). "
                "Enter the modified code within 2 minutes. Use /resend if it expires.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ENTER_CODE
        else:
            await update.message.reply_text("Already authorized!")
            await _clean_up_client(client)
            return ConversationHandler.END
            
    except PhoneNumberInvalidError:
        await update.message.reply_text("Invalid phone number. Please try /authorize again.")
        return ConversationHandler.END
    except FloodWaitError as e:
        await update.message.reply_text(
            f"Too many attempts. Please wait {e.seconds} seconds and try /authorize again."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Authorization initiation error: {e}")
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the obfuscated code input."""
    # Validate active session
    if not _validate_session(context):
        await update.message.reply_text(AUTH_ERROR_MSG)
        return ConversationHandler.END

    client = context.user_data['client']
    phone_number = context.user_data['phone_number']
    
    try:
        # Process and decode the obfuscated code
        obfuscated_code = update.message.text.strip()
        try:
            obfuscated_code = int(obfuscated_code)
            real_code = str(obfuscated_code - OBFUSCATION_CONSTANT)
        except ValueError:
            await update.message.reply_text(
                f"Please send a numeric code. Add {OBFUSCATION_CONSTANT} to the Telegram code and try again."
            )
            return ENTER_CODE

        # Attempt sign-in with the decoded code
        await client.sign_in(phone_number, real_code)
        await update.message.reply_text("Authorization successful!")
        await _clean_up_session(client, context)
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
        await _clean_up_session(client, context)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Code sign-in error: {e}")
        await update.message.reply_text(
            f"Invalid code or error: {e}. Ensure you added {OBFUSCATION_CONSTANT} "
            "to the Telegram code. Use /resend for a new code or /cancel to stop."
        )
        return ENTER_CODE


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the user's password for two-factor authentication."""
    # Validate active session
    if not _validate_session(context):
        await update.message.reply_text(AUTH_ERROR_MSG)
        return ConversationHandler.END

    client = context.user_data['client']
    password = update.message.text.strip()

    try:
        # Attempt sign-in with password
        await client.sign_in(password=password)
        await update.message.reply_text("Authorization successful with 2FA!")
        await _clean_up_session(client, context)
        return ConversationHandler.END
        
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try again.")
        await _clean_up_session(client, context)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Password sign-in error: {e}")
        await update.message.reply_text(
            f"Invalid password or error: {e}. Please try again or use /cancel to stop."
        )
        return ENTER_PASSWORD


async def resend_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Resend the authorization code."""
    # Get client and phone number from context
    client = context.user_data.get('client')
    phone_number = context.user_data.get('phone_number')
    
    if not client or not phone_number:
        await update.message.reply_text(AUTH_ERROR_MSG)
        return ConversationHandler.END
    
    try:
        # Request new code
        await client.send_code_request(phone_number, force_sms=False)
        await update.message.reply_text(
            f"A new code was sent to {phone_number}. "
            f"Add {OBFUSCATION_CONSTANT} to it (e.g., 12345 becomes {12345 + OBFUSCATION_CONSTANT}) "
            "and enter the modified code within 2 minutes."
        )
        return ENTER_CODE
        
    except FloodWaitError as e:
        await update.message.reply_text(f"Too many attempts. Please wait {e.seconds} seconds and try again.")
        await _clean_up_session(client, context)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Resend code error: {e}")
        await update.message.reply_text(f"Error resending code: {e}. Try /authorize again.")
        await _clean_up_session(client, context)
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the authorization process."""
    client = context.user_data.get('client')
    if client:
        await client.disconnect()
    context.user_data.clear()
    await update.message.reply_text("Cancelled process")
    return ConversationHandler.END


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Log out the user."""
    user_id = update.effective_user.id
    session_name = f"{SESSION_PREFIX}{user_id}"
    
    if await is_authorized(session_name):
        async with create_telegram_client(session_name) as client:
            await client.log_out()
        await update.message.reply_text("You have been logged out.")
    else:
        await update.message.reply_text("You are not logged in.")
    
    return ConversationHandler.END


def _validate_session(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Validate if a session is active.
    
    Returns:
        bool: True if session is active, False otherwise.
    """
    return 'client' in context.user_data and 'phone_number' in context.user_data


async def _clean_up_client(client) -> None:
    """Disconnect the client."""
    if client:
        await client.disconnect()


async def _clean_up_session(client, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disconnect the client and clear user data."""
    await _clean_up_client(client)
    context.user_data.clear()