from langchain_community.chat_models import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from ..data_model import Intent, Route
from .base import BaseAgent

COORDINATOR_PROMPT = """
You are an advanced assistant

Task: structure user request into a **Route** object for downstream processing.

## Context
## Agent/Intent
Each agent has a set of valid intents.  
- **Intent** = current user intent.  
- **Agent** = processor for that intent.  
- Intent and agent **must** match.  
```
{agent_intents}
```

## Route Schema
```
intent_resolution:
  intent: string # represents user intent name
  agent: string # processor agent for that intent
  confidence: float # confidence level (0.0-1.0) in the intent resolution
  parameters: dict # optional parameters for the intent
topic: string # A 1-2 sentence summary representing actual conversation topic
keywords: array<string> # relevant keywords from current conversation
```

## Response Template (strict)
You must respond with ONLY a valid JSON object that matches the Route schema exactly. No additional text, explanations, or formatting.


### Step-by-Step Instructions

#### Topic
1. **Choose Topic** – Create a concise topic or reuse the most relevant one from `{prev_topics}` if continuation.  
2. **Direct Intent Only** – Identify only the direct intent of the latest message (no hidden or indirect meanings).  

#### Intent Resolution
3. **Check Relevance Scores** – Review all candidate intents and note their relevance scores (0.0-1.0).  
4. **Prioritize Highest Score** – prioritize the intent with the highest relevance scores.
5. **Example Verification** - Validate latest user message against few-shot examples.
6. **Validate Agent** – Ensure the chosen intent is valid for the selected agent.  
7. **No Mixing** – Do not combine intents and agents from different contexts; they must stay aligned.  
8. **Verification** - Confirm that selected intent represents the most likely user intent of last message.

Respond with ONLY the JSON object:
"""

coordinator_prompt_template = ChatPromptTemplate.from_messages(
    [("system", COORDINATOR_PROMPT), MessagesPlaceholder(variable_name="messages")]
)


class CoordinatorAgent(BaseAgent):
    """
    Agent that retrieves unread message history from Telegram and generates summaries.
    """

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def run(self, messages, agent_intents="", prev_topics=""):
        # Format the coordinator prompt with the provided context
        # Create JSON output parser
        json_parser = JsonOutputParser()

        # Create the chain by combining the prompt template with the LLM and JSON parser
        chain = coordinator_prompt_template | self.llm | json_parser

        try:
            # Run the chain with the formatted inputs and messages
            json_result = chain.invoke(
                {
                    "agent_intents": agent_intents,
                    "prev_topics": prev_topics,
                    "messages": messages,
                }
            )

            # Convert JSON result to Route object
            intent_data = json_result.get("intent_resolution", {})
            intent = Intent(
                intent=intent_data.get("intent", "unknown"),
                agent=intent_data.get("agent", "unknown"),
                confidence=float(intent_data.get("confidence", 0.0)),
                parameters=intent_data.get("parameters", {}),
            )

            route = Route(
                intent_resolution=intent,
                topic=json_result.get("topic", "No topic identified"),
                keywords=json_result.get("keywords", []),
            )

            return route

        except Exception as e:
            # Fallback to a default Route object if parsing fails
            print(f"Warning: Failed to parse LLM output to Route object: {e}")
            fallback_intent = Intent(
                intent="unknown", agent="unknown", confidence=0.0, parameters={}
            )
            return Route(
                intent_resolution=fallback_intent,
                topic="Failed to parse user intent",
                keywords=[],
            )
