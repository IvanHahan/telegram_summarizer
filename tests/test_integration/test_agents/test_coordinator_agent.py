import pytest

from langgraph_app.agents.coordinator_agent import CoordinatorAgent
from langgraph_app.data_model import Intent, Route


@pytest.fixture
def coordinator_agent(llm):
    return CoordinatorAgent(llm)


def test_agent_run_returns_route_object(coordinator_agent):
    messages = [{"role": "user", "content": "Generate sales report for last month"}]
    agent_intents = """
    unread_agent:
    - summarize_unread_messages: Get summary of unread messages
    - mark_as_read: Mark messages as read
    """

    response = coordinator_agent.run(
        messages=messages,
        agent_intents=agent_intents,
        prev_topics="Previous conversation about message summaries",
    )

    # Verify that response is a Route object
    assert isinstance(response, Route)
    assert hasattr(response, "intent_resolution")
    assert hasattr(response, "topic")
    assert hasattr(response, "keywords")

    # Verify intent_resolution is an Intent object
    assert isinstance(response.intent_resolution, Intent)
    assert hasattr(response.intent_resolution, "intent")
    assert hasattr(response.intent_resolution, "agent")
    assert hasattr(response.intent_resolution, "confidence")
    assert hasattr(response.intent_resolution, "parameters")

    # Verify confidence is between 0 and 1
    assert 0.0 <= response.intent_resolution.confidence <= 1.0

    # Verify topic is a string
    assert isinstance(response.topic, str)
    assert len(response.topic) > 0

    # Verify keywords is a list
    assert isinstance(response.keywords, list)
