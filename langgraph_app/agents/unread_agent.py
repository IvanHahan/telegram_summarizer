from langchain.prompts import PromptTemplate

from ..data_model import AgentResponse, IntentNames, IntentSpec, Route
from ..machines.unread_machine import UnreadMachine
from ..prompts import SUMMARIZE_PROMPT_TEMPLATE
from ..utils.formatting import format_chats
from ..utils.telegram_utils import create_telegram_handler
from .base import BaseAgent


class UnreadHistoryAgent(BaseAgent):
    """
    Agent that retrieves unread message history from Telegram and generates summaries.
    """

    name = "UnreadHistoryAgent"
    description = "Retrieves unread messages from Telegram chats and generates intelligent summaries"

    def __init__(self, llm, user_id: str = None, telegram_handler=None):
        """
        Initialize the UnreadHistoryAgent.

        Args:
            user_id (str): Telegram user ID for session management
        """
        self.user_id = user_id
        self.llm = llm
        self.telegram_handler = telegram_handler or create_telegram_handler(
            user_id
        )  # Optional custom Telegram handler
        self.machine = UnreadMachine()
        self.response = None
        self.unread_chats = None
        self._setup_callbacks()

    def _setup_callbacks(self):
        """
        Setup callbacks for the state machine.
        """
        # Assign condition methods to the machine
        self.machine.is_unhandled = self.is_unhandled
        self.machine.is_unread_history = self.is_unread_history
        self.machine.is_yes = self.is_yes
        self.machine.is_mark_as_read = self.is_mark_as_read
        self.machine.is_no = self.is_no

        # Assign before callback methods to the machine
        self.machine.before_reset = self.before_reset
        self.machine.before_fallback = self.before_fallback
        self.machine.before_get_unread_history = self.before_get_unread_history
        self.machine.before_mark_as_read = self.before_mark_as_read
        self.machine.before_finalize = self.before_finalize

        # Assign after callback methods to the machine
        self.machine.after_reset = self.after_reset
        self.machine.after_fallback = self.after_fallback
        self.machine.after_get_unread_history = self.after_get_unread_history
        self.machine.after_mark_as_read = self.after_mark_as_read
        self.machine.after_finalize = self.after_finalize

    @property
    def intents(self) -> list[str]:
        """
        Define the intents this agent can handle.

        Returns:
            list[str]: List of supported intents
        """

        summarize_unread_intent = IntentSpec(
            name=IntentNames.summarize_unread,
            description="Summarize unread messages from Telegram",
            examples=[
                "Summarize my unread messages",
                "What are my unread messages?",
            ],
            parameters={
                "include_groups": "include group chats in the summary",
                "include_private": "include private chats in the summary",
                "include_channels": "include channels in the summary",
                "include_muted": "include muted chats in the summary",
            },
        )
        mark_as_read_intent = IntentSpec(
            name=IntentNames.mark_as_read,
            description="Mark unread messages as read in Telegram",
            examples=[
                "Mark my unread messages as read",
                "I want to mark all my unread messages as read",
            ],
            parameters={},
        )
        return [summarize_unread_intent, mark_as_read_intent]

    def set_initial_state(self):
        """
        Set the initial state of the state machine.

        Args:
            state (str): The initial state to set. Defaults to 'idle'.
        """
        pass

    def execute_transition(self) -> bool:
        """
        Execute a state machine transition.

        Args:
            trigger (str): The trigger/transition name to execute
            *args: Additional positional arguments to pass to the trigger
            **kwargs: Additional keyword arguments to pass to the trigger

        Returns:
            bool: True if transition was successful, False otherwise
        """
        if self.machine.is_idle():
            self.machine.get_unread_history() or self.machine.fallback()
        elif self.machine.is_wait_mark_as_read():
            self.machine.mark_as_read() or self.machine.finalize() or self.machine.fallback()

    def run(
        self, route: Route, max_chats: int = 10, max_words: int = 10000, **kwargs
    ) -> dict:
        """
        Retrieve unread history and generate a summary.

        Args:
            user_id (str): User ID for Telegram session
            include_groups (bool): Include group chats in results
            include_private (bool): Include private chats in results
            include_channels (bool): Include channels in results
            include_muted (bool): Include muted chats in results
            max_chats (int): Maximum number of chats to process
            max_words (int): Maximum total words to process
            **kwargs: Additional arguments

        Returns:
            dict: Dictionary containing unread chats and generated summary
        """
        self.route = route
        self.set_initial_state()
        self.execute_transition()
        return self.response

    def _generate_summary(self, unread_chats: list) -> str:
        """
        Generate an intelligent summary of unread chats using LLM.

        Args:
            unread_chats (list): List of unread chat data

        Returns:
            str: Generated summary text
        """
        if not unread_chats:
            return "No unread messages to summarize."

        try:
            # Format chats for prompt
            formatted_chats = format_chats(unread_chats)

            # Create summarization prompt
            summarization_prompt = PromptTemplate(
                input_variables=["chats"],
                template=SUMMARIZE_PROMPT_TEMPLATE,
            )

            # Generate summary using LLM
            response = (summarization_prompt | self.llm).invoke(
                input={"chats": formatted_chats}
            )

            # Extract content from response
            if hasattr(response, "content"):
                return response.content
            else:
                return str(response)

        except Exception as e:
            return f"Error generating summary: {str(e)}"

    def summarize_existing_chats(self, unread_chats: list) -> str:
        """
        Generate summary for already retrieved unread chats.

        Args:
            unread_chats (list): List of unread chat data

        Returns:
            str: Generated summary text
        """
        return self._generate_summary(unread_chats)

    # State machine condition methods
    def is_unhandled(self) -> bool:
        """Check if the event is unhandled"""
        return True

    def is_unread_history(self) -> bool:
        """Check if there is unread history"""

        return self.route.intent_resolution.intent == IntentNames.summarize_unread

    def is_yes(self) -> bool:
        """Check if the answer is yes"""
        return self.route.intent_resolution.intent == IntentNames.agree

    def is_mark_as_read(self) -> bool:
        """Check if mark as read is requested"""
        return self.route.intent_resolution.intent == IntentNames.mark_as_read

    def is_no(self) -> bool:
        """Check if the answer is no"""
        return self.route.intent_resolution.intent == IntentNames.disagree

    # State machine before callback methods
    def before_reset(self):
        """Called before reset transition"""
        # TODO: Implement before reset logic
        # Example: self.clear_cache(), self.reset_counters()
        pass

    def before_fallback(self):
        """Called before fallback transition"""
        # TODO: Implement before fallback logic
        # Example: self.log_error(), self.cleanup_resources()
        pass

    def before_get_unread_history(self):
        """Called before get_unread_history transition"""
        self.unread_chats = self.telegram_handler.get_unread_chats(
            **self.route.intent_resolution.parameters
        )
        if self.unread_chats:
            summary = self._generate_summary(self.unread_chats)
            self.response = AgentResponse(response=summary, actions=["mark_as_read"])
        else:
            self.response = AgentResponse(
                response="No unread messages found.", actions=[]
            )

    def before_mark_as_read(self):
        """Called before mark_as_read transition"""
        if self.unread_chats is not None:
            chat_ids = [chat["id"] for chat in self.unread_chats]
        else:
            self.unread_chats = self.telegram_handler.get_unread_chats(
                **self.route.intent_resolution.parameters
            )
            chat_ids = [chat["id"] for chat in self.unread_chats]
        if chat_ids:
            self.telegram_handler.mark_chats_as_read(chat_ids=chat_ids)
            self.response = AgentResponse(
                response="All unread messages have been marked as read.",
            )
        else:
            self.response = AgentResponse(
                response="No unread messages found.",
            )

    def before_finalize(self):
        """Called before finalize transition"""
        self.response = AgentResponse(
            response="Session finalized.",
        )

    # State machine after callback methods
    def after_reset(self):
        """Called after reset transition - now in idle state"""
        # TODO: Implement after reset logic
        # Example: self.initialize_defaults(), self.notify_reset_complete()
        pass

    def after_fallback(self):
        """Called after fallback transition - now in idle state"""
        # TODO: Implement after fallback logic
        # Example: self.send_error_notification(), self.reset_to_safe_state()
        pass

    def after_get_unread_history(self):
        """Called after get_unread_history transition - now in wait_mark_as_read state"""
        # TODO: Implement after get_unread_history logic
        # Example: self.present_summary(), self.prompt_user_for_action()
        pass

    def after_mark_as_read(self):
        """Called after mark_as_read transition - now in idle state"""
        # TODO: Implement after mark_as_read logic
        # Example: self.telegram_handler.mark_messages_as_read(), self.send_confirmation()
        pass

    def after_finalize(self):
        """Called after finalize transition - now in idle state"""
        # TODO: Implement after finalize logic
        # Example: self.save_session_data(), self.send_final_summary()
        pass
