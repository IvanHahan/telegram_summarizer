
from dataclasses import dataclass


class IntentNames:
    summarize_unread = "summarize_unread_messages"
    mark_as_read = "mark_as_read"
    agree = "agree"
    disagree = "disagree"

@dataclass
class Intent:
    intent: str
    agent: str
    confidence: float
    parameters: dict = None

@dataclass
class Route:
    intent_resolution: Intent
    topic: str
    keywords: list[str] = None

@dataclass
class IntentSpec:
    name: str
    description: str
    examples: list[str] = []
    weight: float = 1.0
    parameters: dict = None


@dataclass
class AgentResponse:
    response: str
    actions: list[str] = None