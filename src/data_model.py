from typing import Dict, List

from pydantic import BaseModel, Field


class IntentNames:
    summarize_unread = "summarize_unread_messages"
    mark_as_read = "mark_as_read"
    agree = "agree"
    disagree = "disagree"


class Intent(BaseModel):
    intent: str
    agent: str
    confidence: float
    parameters: Dict = Field(default_factory=dict)


class Route(BaseModel):
    intent_resolution: Intent
    topic: str
    keywords: List[str] = Field(default_factory=list)


class IntentSpec(BaseModel):
    name: str
    description: str
    examples: List[str] = Field(default_factory=list)
    weight: float = 1.0
    parameters: Dict = Field(default_factory=dict)


class AgentResponse(BaseModel):
    response: str
    actions: List[str] = Field(default_factory=list)
