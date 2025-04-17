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
    receive_code,
    receive_contact,
    receive_password,
    resend_code,
)
from telegram_bot.store import create_store
from telegram_bot.telegram_utils import (
    create_telegram_client,
    get_chat_history,
    is_authorized,
    search_chat,
)
from telegram_bot.workflow import (
    analyze_chat_workflow,
    mark_as_read_workflow,
    unread_history_workflow,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
store = create_store('async_redis')

# Conversation state constants
SHARE_CONTACT, ENTER_CODE, ENTER_PASSWORD = range(3)
ENTER_CHAT_QUERY, SELECT_CHAT = range(2)

OBFUSCATION_CONSTANT = 1000


def get_thread_id(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Generate or retrieve a thread ID from context."""
    if 'thread_id' not in context.user_data:
        context.user_data['thread_id'] = uuid.uuid4().hex
    return context.user_data['thread_id']


async def is_bot_authorized(update: Update) -> bool:
    """Check if the current user is authorized."""
    user_id = update.effective_user.id
    session_name = f"session_{user_id}"
    return await is_authorized(session_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not await is_bot_authorized(update):
        await authorize(update, context)
    else:
        await update.message.reply_text(
            "You are already authorized. Use /summary to get your unread messages."
        )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display unread messages; offer marking them as read."""
    if await is_bot_authorized(update):
        user_id = update.effective_user.id
        workflow = await unread_history_workflow()
        res = await workflow.ainvoke(
            {'user_id': f"session_{user_id}"},
            config={'thread_id': get_thread_id(context)}
        )
        context.user_data['unread_chats'] = res.get('unread_chats')
        await update.message.reply_text(res['messages'][-2].content)
        keyboard = [
            [InlineKeyboardButton("Mark as Read", callback_data="mark_as_read")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(res['messages'][-1].content, reply_markup=reply_markup)
    else:
        await authorize(update, context)


async def mark_as_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mark-as-read action via callback query."""
    if await is_bot_authorized(update):
        user_id = update.effective_user.id
        workflow = await mark_as_read_workflow()
        res = await workflow.ainvoke(
            {
                'user_id': f"session_{user_id}",
                'unread_chats': context.user_data.get('unread_chats')
            },
            config={'thread_id': get_thread_id(context)}
        )
        context.user_data.pop('unread_chats', None)
        await update.callback_query.edit_message_text(res['messages'][-1].content)
    else:
        await authorize(update, context)


# --- Analyze Conversation Handlers ---
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start /analyze conversation by asking the user for a chat query."""
    if not await is_bot_authorized(update):
        await authorize(update, context)
        return ConversationHandler.END

    await update.message.reply_text(
        "Please enter the name or ID of the chat you want to analyze:",
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

    async with create_telegram_client(f"session_{user_id}") as client:
        results = await search_chat(client, query, top_k=5)

    # If the result is a single chat, analyze immediately
    if isinstance(results, dict):
        return await analyze_selected_chat(update, context, results)

    if not results:
        await update.message.reply_text(
            "No chats found matching your query. Please try again or /cancel to stop."
        )
        return ENTER_CHAT_QUERY

    context.user_data['chat_results'] = results
    keyboard = [[chat['chat_name']] for chat in results]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "I found the following chats. Please select one:",
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

    async with create_telegram_client(f"session_{user_id}") as client:
        messages = await get_chat_history(client, chat_id)
        selected_chat['messages'] = messages

    workflow = await analyze_chat_workflow()
    state = await workflow.ainvoke(
        {'user_id': f"session_{user_id}", 'selected_chat': selected_chat},
        config={'thread_id': get_thread_id(context)}
    )
    analysis_result = state['messages'][-1].content
    await update.message.reply_text(
        f"Analysis of chat '{chat_name}':\n{analysis_result}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cancel_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the chat analysis conversation."""
    await update.message.reply_text("Chat analysis canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main() -> None:
    """Run the Telegram bot."""
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

    analyze_handler = ConversationHandler(
        entry_points=[CommandHandler("analyze", analyze)],
        states={
            ENTER_CHAT_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_query)],
            SELECT_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_selection)],
        },
        fallbacks=[CommandHandler("cancel", cancel_analyze)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CallbackQueryHandler(mark_as_read, pattern="mark_as_read"))
    application.add_handler(auth_handler)
    application.add_handler(analyze_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()