
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler

from langgraph_app.workflow import analyze_chat_node

from ..utils.analytics import track_event  # new import for analytics logging
from ..utils.localization import t
from ..utils.telegram_utils import create_telegram_client, get_chat_history, search_chat
from .utils import is_bot_authorized

ENTER_CHAT_QUERY, SELECT_CHAT = range(2)


# --- Analyze Conversation Handlers ---
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start /analyze conversation by asking the user for a chat query."""
    user_id = update.effective_user.id
    await track_event(user_id, "analyze_executed")  # analytics logging added

    if not await is_bot_authorized(update):
        await update.message.reply_text(t(user_id, "start_unauth"))
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

    state = get_state(context)
    state['selected_chat'] = selected_chat
    state = analyze_chat_node(state)
    set_state(context, state)
    analysis_result = state['messages'][-1].content
    await update.message.reply_text(
        f"Analysis of chat '{chat_name}':\n{analysis_result}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END