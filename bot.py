import logging
import os
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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

from login_handler import (
    authorize,
    cancel,
    logout,
    receive_code,
    receive_contact,
    receive_password,
    resend_code,
)
from telegram_bot.localization import LANGUAGES, t
from telegram_bot.store import store
from telegram_bot.telegram_utils import (
    create_telegram_client,
    get_chat_history,
    is_authorized,
    search_chat,
)
from telegram_bot.workflow import (
    analyze_chat_workflow,
    chat_workflow,
    mark_as_read_workflow,
    unread_history_workflow,
)

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


def get_thread_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Generate or retrieve a thread ID from context."""
    if 'thread_id' not in context.user_data:
        user_id = update.effective_user.id
        if store.exists(f'thread_id:{str(user_id)}'):
            context.user_data['thread_id'] = store.get(f'thread_id:{str(user_id)}')
        else:
            thread_id = uuid.uuid4().hex
            store.set(f'thread_id:{str(user_id)}', thread_id, expire=3600)
            context.user_data['thread_id'] = thread_id
    return context.user_data['thread_id']


async def is_bot_authorized(update: Update) -> bool:
    """Check if the current user is authorized."""
    user_id = update.effective_user.id
    return await is_authorized(user_id)


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

    # load persisted language if any
    saved_lang = store.get(f"lang:{user_id}")
    if saved_lang:
        context.user_data["lang"] = saved_lang

    if not await is_bot_authorized(update):
        user_id = update.effective_user.id
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
    if await is_bot_authorized(update):
        user_id = update.effective_user.id
        workflow = await unread_history_workflow()
        res = await workflow.ainvoke(
            {'user_id': str(user_id)},
            config={'thread_id': get_thread_id(update, context)}
        )
        context.user_data['unread_chats'] = res.get('unread_chats')
        if context.user_data['unread_chats']:
            await update.message.reply_text(res['messages'][-2].content)
            keyboard = [
                [InlineKeyboardButton(t(user_id, "action_mark_as_read"), callback_data="mark_as_read")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                res['messages'][-1].content,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(res['messages'][-1].content)

    else:
        user_id = update.effective_user.id
        await update.message.reply_text(
            t(user_id, "start_unauth"),
            reply_markup=get_actions_keyboard()
        )


async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mark-as-read action via callback query."""
    if await is_bot_authorized(update):
        user_id = update.effective_user.id
        workflow = await mark_as_read_workflow()
        res = await workflow.ainvoke(
            {
                'user_id':str(user_id),
                'unread_chats': context.user_data.get('unread_chats')
            },
            config={'thread_id': get_thread_id(update, context)}
        )
        context.user_data.pop('unread_chats', None)
        await update.callback_query.edit_message_text(res['messages'][-1].content)
    else:
        user_id = update.effective_user.id
        # Inform user to start authorization
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            t(user_id, "start_unauth")
        )


# --- Analyze Conversation Handlers ---
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start /analyze conversation by asking the user for a chat query."""
    user_id = update.effective_user.id
    if not await is_bot_authorized(update):
        await update.message.reply_text(
            t(user_id, "start_unauth")
        )
        return ConversationHandler.END

    await update.message.reply_text(
        t(user_id, "ask_chat_query"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENTER_CHAT_QUERY


async def handle_chat_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle chat query by searching for chats matching the entry.
    If the result is a single chat (dict), perform analysis immediately.
    Otherwise, prompt user to select a chat from a list.
    """
    query = update.message.text
    user_id = update.effective_user.id

    async with create_telegram_client(user_id) as client:
        results = await search_chat(client, query, top_k=5)

    # If the result is a single chat, analyze immediately
    if isinstance(results, dict):
        return await analyze_selected_chat(update, context, results)

    if not results:
        await update.message.reply_text(t(user_id, "no_chats_found"))
        return ENTER_CHAT_QUERY

    context.user_data['chat_results'] = results
    keyboard = [[chat['chat_name']] for chat in results]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        t(user_id, "select_chat"),
        reply_markup=reply_markup,
    )
    return SELECT_CHAT


async def handle_chat_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's chat selection and analyze the selected chat."""
    selected_chat_title = update.message.text
    chat_results = context.user_data.get('chat_results', [])
    selected_chat = next((chat for chat in chat_results if chat['chat_name'] == selected_chat_title), None)

    if not selected_chat:
        await update.message.reply_text(
            "Invalid selection. Please select a chat from the list or /cancel to stop."
        )
        return SELECT_CHAT

    return await analyze_selected_chat(update, context, selected_chat)


async def analyze_selected_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_chat: dict) -> int:
    """Perform chat analysis for the given chat and reply with the analysis result."""
    user_id = update.effective_user.id
    chat_id = selected_chat['chat_id']
    chat_name = selected_chat['chat_name']

    async with create_telegram_client(user_id) as client:
        messages = await get_chat_history(client, chat_id)
        selected_chat['messages'] = messages

    workflow = await analyze_chat_workflow()
    state = await workflow.ainvoke(
        {'user_id': str(user_id), 'selected_chat': selected_chat},
        config={'thread_id': get_thread_id(update, context)}
    )
    analysis_result = state['messages'][-1].content
    await update.message.reply_text(
        f"Analysis of chat '{chat_name}':\n{analysis_result}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    user_id = update.effective_user.id
    session_name = user_id

    if not await is_bot_authorized(update):
        await update.message.reply_text(
            t(user_id, "start_unauth")
        )
        return

    # Process the incoming message
    workflow = chat_workflow()
    state = await workflow.ainvoke(
        {'user_id': str(session_name), 'messages': [update.message.text]},
        config={'thread_id': get_thread_id(update, context)}
    )
    response = state['messages'][-1].content
    await update.message.reply_text(response)

    chats_to_select = state.get('chats_to_select')
    if chats_to_select:
        await workflow.aupdate_state(
            {'configurable': {'thread_id': get_thread_id(update, context)}},
            {'chats_to_select': None}
        )
        context.user_data['chat_results'] = chats_to_select
        keyboard = [[chat['chat_name']] for chat in chats_to_select]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            t(user_id, "select_chat"),
            reply_markup=reply_markup,
        )
        return SELECT_CHAT

    unread_chats = state.get('unread_chats')
    if unread_chats:
        await workflow.aupdate_state(
            {'configurable': {'thread_id': get_thread_id(update, context)}},
            {'unread_chats': None}
        )
        context.user_data['unread_chats'] = unread_chats
        keyboard = [
            [InlineKeyboardButton(t(user_id, "action_mark_as_read"), callback_data="mark_as_read")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            t(user_id, "ask_mark_read"),
            reply_markup=reply_markup,
        )


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

    chat_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
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
    application.add_handler(chat_handler)

    # Add help handler
    application.add_handler(
        CommandHandler("help", lambda u, c: c.bot.send_message(u.effective_chat.id, t(u.effective_user.id, "help_text")))
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()