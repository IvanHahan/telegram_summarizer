import logging
import os

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.redis import AsyncRedisSaver
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)

from telegram_bot.telegram_utils import is_authorized

from .workflow import create_workflow

logger = logging.getLogger(__name__)

async def ask_bot(workflow, user_id: str, message: str):
    state = await workflow.ainvoke(
            {'messages': [HumanMessage(message)], 'user_id': str(user_id)}, config={'thread_id': user_id}
        )
    return state


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

async def authorization_handler(update: Update):
    user_id = update.effective_user.id
    if not await is_authorized(str(user_id)):
        button = KeyboardButton(text="Share your phone number", request_contact=True)
        keyboard = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Please share your phone number:", reply_markup=keyboard)
        return False
    return True

async def ask_bot(workflow, message, user_id, session_id, action='message'):
    state = await workflow.ainvoke(
            {'messages': [HumanMessage(message)], 'user_id': str(user_id), 'action': action}, config={'thread_id': str(user_id)}
        )
    return state

async def bot_handler(update: Update, session_id: str, message: str = None, action: str = 'message'):
    if await authorization_handler(update):
        async with AsyncRedisSaver.from_conn_info(
            host=os.getenv("REDIS_HOST", "localhost"), 
            port=os.getenv("REDIS_PORT", 6379), 
            db=0
        ) as checkpointer:
            checkpointer.clear
            workflow = create_workflow(checkpointer)
            user_id = update.effective_user.id
            user_message = update.message.text
            if message:
                user_message = message
            try:
                # Process the message through the bot
                state = await ask_bot(workflow, user_message, user_id, session_id, action)

                checkpointer.conn

                # Handle bot response
                await send_bot_response(update, state)
                
                # Handle any follow-up actions from the state
                await process_follow_up_actions(update, state)
                
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}: {str(e)}")
                await update.message.reply_text(
                    "Sorry, I encountered an error while processing your message."
                )

async def get_state(user_id: str):
    async with AsyncRedisSaver.from_conn_info(
        host=os.getenv("REDIS_HOST", "localhost"), 
        port=os.getenv("REDIS_PORT", 6379), 
        db=0
    ) as checkpointer:
        workflow = create_workflow(checkpointer)
        checkpoint = await workflow.aget_state({'configurable': {'thread_id': str(user_id)}})
        return checkpoint.values
    
async def set_state(user_id: str, state: dict):
    async with AsyncRedisSaver.from_conn_info(
        host=os.getenv("REDIS_HOST", "localhost"), 
        port=os.getenv("REDIS_PORT", 6379), 
        db=0
    ) as checkpointer:
        workflow = create_workflow(checkpointer)
        await workflow.aupdate_state({'configurable': {'thread_id': str(user_id)}}, state)
    