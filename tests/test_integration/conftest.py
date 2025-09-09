import pytest
from langchain_community.chat_models import ChatOpenAI


@pytest.fixture
def llm():
    return ChatOpenAI(model="gpt-4.1-nano", temperature=0)
