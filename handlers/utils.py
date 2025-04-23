
from telegram import Update

from ..utils.store import store
from ..utils.telegram_utils import is_authorized


def get_state(update: Update) -> dict:
    """Get the current state from context."""
    # return context.user_data.get('state', {'user_id': str(update.effective_user.id), 'messages': []})
    state = store.get_object(str(update.effective_user.id))
    if not state:
        state = {'user_id': str(update.effective_user.id), 'messages': []}
    return state

def set_state(update: Update, state: dict) -> None:
    """Set the current state in context."""
    # context.user_data['state'] = state
    store.set_object(str(update.effective_user.id), state.to_dict())


async def is_bot_authorized(update: Update) -> bool:
    """Check if the current user is authorized."""
    user_id = update.effective_user.id
    return await is_authorized(user_id)