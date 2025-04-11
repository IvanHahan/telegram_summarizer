import json
from copy import copy

import redis
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

redis_client = redis.StrictRedis(host="localhost", port=6379, db=0, decode_responses=True)

async def save_user_state(user_id: int, state: dict) -> None:
    """Save user state to Redis."""
    messages = [msg.to_json() for msg in state['messages']]
    state = copy(state)
    state['messages'] = messages
    redis_client.set(f"user:{user_id}:state", json.dumps(state))

def message_decoder(data):
    if isinstance(data, dict) and "id" in data and "kwargs" in data:
        class_id = data["id"]
        kwargs = data["kwargs"]
        if class_id[-1] == "HumanMessage":
            return HumanMessage(**kwargs)
        elif class_id[-1] == "AIMessage":
            return AIMessage(**kwargs)
        elif class_id[-1] == "ToolMessage":
            return ToolMessage(**kwargs)
    return data

async def get_user_state(user_id: int) -> dict:
    """Retrieve user state from Redis."""
    state = redis_client.get(f"user:{user_id}:state")
    state = json.loads(state) if state else {}
    if state.get('messages'):
        state['messages'] = [message_decoder(msg) for msg in state['messages']] 
    return state


async def clear_user_state(user_id: int) -> None:
    """Clear user state from Redis."""
    redis_client.delete(f"user:{user_id}:state")