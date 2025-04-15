import logging
import os
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
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
from telegram_bot.workflow import mark_as_read_workflow, unread_history_workflow

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
store = create_store('async_redis')


# Conversation states
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)
MARK_AS_READ = 0

# Obfuscation constant
OBFUSCATION_CONSTANT = 1000

def get_thread_id(context: ContextTypes.DEFAULT_TYPE):
    if not 'thread_id' in context.user_data:
        context.user_data['thread_id'] = uuid.uuid4().hex
    session_id = context.user_data.get('thread_id')
    return session_id

async def is_bot_authorized(update: Update):
    """Check if the user is authorized."""
    user_id = update.effective_user.id
    session_name = f"session_{user_id}"
    return await is_authorized(session_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not await is_bot_authorized(update):
        authorize(update, context)
    else:
        await update.message.reply_text(
            "You are already authorized. Use /summary to get your unread messages."
        )

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if await is_bot_authorized(update):
        workflow = await unread_history_workflow()
        res = await workflow.ainvoke({'user_id': 'session_' + str(update.effective_user.id)}, config={'thread_id': get_thread_id(context)})
        context.user_data['unread_chats'] = res['unread_chats']
        await update.message.reply_text(res['messages'][-2].content)
        keyboard = [
            [InlineKeyboardButton("Mark as Read", callback_data="mark_as_read", )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(res['messages'][-1].content, reply_markup=reply_markup)
    else:
        await authorize(update, context)

async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /mark_as_read command."""
    if await is_bot_authorized(update):
        workflow = await mark_as_read_workflow()
        res = await workflow.ainvoke({'user_id': 'session_' + str(update.effective_user.id),
                                      'unread_chats': context.user_data.get('unread_chats')}, 
                                     config={'thread_id': get_thread_id(context)})
        if 'unread_chats' in context.user_data:
            del context.user_data['unread_chats']
        await update.callback_query.edit_message_text(res['messages'][-1].content)
    else:
        await authorize(update, context)

def main() -> None:
    """Run the bot."""
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

    auth_handler = ConversationHandler(
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

    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(
        CallbackQueryHandler(mark_as_read, pattern="mark_as_read")
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(auth_handler)
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recieve_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()