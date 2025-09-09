from unittest.mock import Mock, patch

import pytest

from langgraph_app.agents.unread_agent import UnreadHistoryAgent
from langgraph_app.data_model import Intent, IntentNames, Route


@pytest.fixture
def mock_telegram_handler():
    """Create a mock telegram handler"""
    mock_handler = Mock()
    mock_handler.get_unread_chats.return_value = [
        {
            "chat_name": "Test Private Chat",
            "chat_id": 12345,
            "unread_count": 3,
            "is_channel": False,
            "is_group": False,
            "id": 12345,
            "messages": [
                {
                    "text": "Hello, how are you?",
                    "sender_name": "Alice",
                    "sender_id": 111,
                },
                {
                    "text": "Are we still meeting today?",
                    "sender_name": "Alice",
                    "sender_id": 111,
                },
                {"text": "Let me know!", "sender_name": "Alice", "sender_id": 111},
            ],
        },
        {
            "chat_name": "Work Group",
            "chat_id": 67890,
            "unread_count": 2,
            "is_channel": False,
            "is_group": True,
            "id": 67890,
            "messages": [
                {"text": "Meeting at 3 PM", "sender_name": "Bob", "sender_id": 222},
                {
                    "text": "Thanks for the update",
                    "sender_name": "Charlie",
                    "sender_id": 333,
                },
            ],
        },
    ]
    mock_handler.mark_chats_as_read.return_value = None
    return mock_handler


@pytest.fixture
def agent(llm, mock_telegram_handler):
    """Create an UnreadHistoryAgent instance with mocked dependencies"""
    with patch(
        "langgraph_app.agents.unread_agent.create_telegram_handler",
        return_value=mock_telegram_handler,
    ):
        agent = UnreadHistoryAgent(llm=llm, user_id="test_user_123")
        agent.telegram_handler = mock_telegram_handler
        return agent


@pytest.fixture
def route():
    return Route(
        intent_resolution=Intent(
            intent=IntentNames.summarize_unread,
            agent="unread_agent",
            confidence=0.95,
            parameters={},
        ),
        topic="Summary of unread messages",
        keywords=["summary", "unread", "messages"],
    )


def test_summarize_unread_messages(agent, route):
    """Test the summarize_unread_messages intent"""
    response = agent.run(route)
    assert response
