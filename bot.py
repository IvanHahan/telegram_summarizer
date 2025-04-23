import logging
import os

from langchain_core.messages import HumanMessage
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.analyze_handler import *
from handlers.login_handler import *
from handlers.utils import get_state, is_bot_authorized, set_state
from langgraph_app.workflow import (
    chat_workflow,
    mark_as_read_node,
    suggest_actions_node,
    unread_history_node,
)
from utils.analytics import track_event  # new import for analytics logging
from utils.localization import LANGUAGES, t
from utils.store import store

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation state constants
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)
ENTER_CHAT_QUERY, SELECT_CHAT = range(2)

OBFUSCATION_CONSTANT = 1000

# Action Constants
ACTION_SUMMARY = "/summary"
ACTION_ANALYZE = "/analyze"
ACTION_MARK_AS_READ = "Mark as Read"
ACTION_HELP = "/help"

def get_actions_keyboard() -> ReplyKeyboardMarkup:
    """
    Create and return a custom keyboard with common bot actions.
    """
    keyboard = [
        [ACTION_SUMMARY, ACTION_ANALYZE],
        [ACTION_HELP]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask user to choose language."""
    user_id = update.effective_user.id
    buttons = [
        [InlineKeyboardButton(name, callback_data=f"lang_{code}")]
        for code, name in LANGUAGES.items()
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(t(user_id, "choose_language"), reply_markup=markup)


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection."""
    data = update.callback_query.data  # e.g. "lang_en" or "lang_uk"
    _, code = data.split("_", 1)
    user_id = update.effective_user.id

    # persist in Redis
    store.set(f"lang:{user_id}", code)

    # update in-memory context
    context.user_data["lang"] = code

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(t(user_id, "lang_changed"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_id = update.effective_user.id
    await track_event(user_id, "start_executed")  # analytics logging added

    # load persisted language if any
    saved_lang = store.get(f"lang:{user_id}")
    if saved_lang:
        context.user_data["lang"] = saved_lang

    if not await is_bot_authorized(update):
        await update.message.reply_text(
            t(user_id, "start_unauth"),
            reply_markup=get_actions_keyboard()
        )
    else:
        await update.message.reply_text(
            t(user_id, "start_authorized"),
            reply_markup=get_actions_keyboard()
        )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display unread messages; offer marking them as read."""
    user_id = update.effective_user.id
    await track_event(user_id, "summary_executed")  # analytics logging added

    if await is_bot_authorized(update):
        state = get_state(context)
        state = await unread_history_node(state)
        set_state(context, state)
        if state['unread_chats']:
            await update.message.reply_text(state['messages'][-2].content)
            keyboard = [
                [InlineKeyboardButton(t(user_id, "action_mark_as_read"), callback_data="mark_as_read")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                state['messages'][-1].content,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(state['messages'][-1].content)
    else:
        await update.message.reply_text(
            t(user_id, "start_unauth"),
            reply_markup=get_actions_keyboard()
        )


async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mark-as-read action via callback query."""
    if await is_bot_authorized(update):
        user_id = update.effective_user.id
        state = get_state(context)
        state = await mark_as_read_node(state)
        set_state(context, state)
        await update.callback_query.edit_message_text(state['messages'][-1].content)
    else:
        user_id = update.effective_user.id
        # Inform user to start authorization
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            t(user_id, "start_unauth")
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    user_id = update.effective_user.id
    await track_event(user_id, "message_handler_executed")  # analytics logging added

    if not await is_bot_authorized(update):
        await update.message.reply_text(
            t(user_id, "start_unauth")
        )
        return

    # Process the incoming message
    state = get_state(update, context)
    state['messages'].append(HumanMessage(update.message.text))
    workflow = chat_workflow()
    state = await workflow.ainvoke(state)
    response = state['messages'][-1].content
    state = await suggest_actions_node(
        state
    )
    set_state(context, state)
    suggest_actions_response = state['messages'][-1].content
    actions = suggest_actions_response.split("\n")
    keyboard = [[action] for action in actions if action]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(response, reply_markup=reply_markup)


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation state and reset context."""
    user_id = update.effective_user.id
    # Clear internal conversation-related data
    context.user_data.clear()  # Clear all user data

    await track_event(user_id, "clear_executed")  # analytics logging added for clear action
    await update.message.reply_text(t(user_id, "clear_done"))


# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and notify the user with a localized message."""
    logger.error(f"Exception while handling update {update!r}:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            user_id = update.effective_user.id
            await update.effective_message.reply_text(
                t(user_id, "unexpected_error")
            )
    except Exception:
        logger.error("Failed to send localized error notification to user.", exc_info=True)


def main() -> None:
    """Run the Telegram bot."""
    application = ApplicationBuilder().arbitrary_callback_data(True).token(os.getenv("TELEGRAM_TOKEN")).build()

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

    analyze_handler = ConversationHandler(
        entry_points=[CommandHandler("analyze", analyze)],
        states={
            ENTER_CHAT_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_query)],
            SELECT_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_selection)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add language handlers
    application.add_handler(CommandHandler("language", language))
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))

    # Add other handlers (start, summary, analyze, etc.)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CallbackQueryHandler(mark_as_read, pattern="mark_as_read"))
    application.add_handler(auth_handler)
    application.add_handler(analyze_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Register clear handler
    application.add_handler(CommandHandler("clear", clear))

    # Add help handler
    application.add_handler(
        CommandHandler("help", lambda u, c: c.bot.send_message(u.effective_chat.id, t(u.effective_user.id, "help_text")))
    )

    # Add error handler
    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()