import os
from pathlib import Path
from typing import Any, Dict

from loguru import logger
from pyrogram import Client, filters
from pyrogram.types import KeyboardButton, ReplyKeyboardMarkup
from transitions.extensions.asyncio import AsyncMachine

user_clients = {}
user_flows = {}


async def get_user_client(user_id: int) -> Client:
    if user_id not in user_clients:
        session_file = Path(f"{user_id}")
        client = Client(
            str(session_file),
            api_id=os.getenv("TELEGRAM_API_ID"),
            api_hash=os.getenv("TELEGRAM_API_HASH"),
        )
        await client.connect()
        user_clients[user_id] = client
    return user_clients[user_id]


class AuthorizationMachine(AsyncMachine):
    """
    stateDiagram-v2
    [*] --> idle

    idle --> idle: handle_authorized [is_authorized]
    idle --> await_contact: start_auth [!is_authorized]

    await_contact --> verify_contact: receive_contact
    verify_contact --> await_code: ask_code [is_contact_valid]
    verify_contact --> await_contact: handle_invalid_contact [!is_contact_valid]

    await_code --> authorizing: receive_code
    authorizing --> idle: finalize [is_authorized]
    authorizing --> idle: unhandled [!is_authorized]
    """

    states = ["idle", "await_contact", "verify_contact", "await_code", "authorizing"]

    def __init__(self, user_client, **kwargs):
        """Initialize the authorization state machine."""
        super().__init__(states=self.states, initial="idle", **kwargs)
        self.user_client = user_client

        # Add transitions based on the state diagram
        self.add_transitions(
            [
                # From idle state
                {
                    "trigger": "handle_authorized",
                    "source": "idle",
                    "dest": "idle",
                    "conditions": "is_authorized",
                    "after": "after_handle_authorized",
                },
                {
                    "trigger": "start_auth",
                    "source": "idle",
                    "dest": "await_contact",
                    "unless": "is_authorized",
                    "after": "after_start_auth",
                },
                # From await_contact state
                {
                    "trigger": "receive_contact",
                    "source": "await_contact",
                    "dest": "verify_contact",
                    "after": "after_receive_contact",
                },
                # From verify_contact state
                {
                    "trigger": "ask_code",
                    "source": "verify_contact",
                    "dest": "await_code",
                    "conditions": "is_contact_valid",
                    "after": "after_ask_code",
                },
                {
                    "trigger": "handle_invalid_contact",
                    "source": "verify_contact",
                    "dest": "await_contact",
                    "unless": "is_contact_valid",
                    "after": "after_handle_invalid_contact",
                },
                # From await_code state
                {
                    "trigger": "receive_code",
                    "source": "await_code",
                    "dest": "authorizing",
                    "after": "after_receive_code",
                },
                # From authorizing state
                {
                    "trigger": "finalize",
                    "source": "authorizing",
                    "dest": "idle",
                    "conditions": "is_authorized",
                    "after": "after_finalize",
                },
                {
                    "trigger": "unhandled",
                    "source": "authorizing",
                    "dest": "idle",
                    "conditions": "is_not_authorized",
                    "after": "after_unhandled",
                },
            ]
        )

        # Initialize state data
        self._user_data: Dict[str, Any] = {}
        self._is_authorized = False
        self._contact_valid = False

    # Condition methods
    async def is_authorized(self, client: Client, message) -> bool:
        """Check if user is authorized."""
        return await self.user_client.storage.user_id() is not None

    async def is_contact_valid(self) -> bool:
        """Check if provided contact is valid."""
        return self._contact_valid

    # After callback stubs
    async def after_handle_authorized(self, *args, **kwargs):
        """Called after handling authorized user in idle state."""
        logger.debug("After handling authorized user")

    async def after_start_auth(self, client: Client, message):
        """Called after starting authentication process."""
        logger.debug("After starting authentication")
        user_id = message.from_user.id
        # Create contact sharing keyboard
        contact_button = KeyboardButton("Share Contact", request_contact=True)
        keyboard = ReplyKeyboardMarkup(
            [[contact_button]], one_time_keyboard=True, resize_keyboard=True
        )

        client.add_handler(
            client.on_message(filters.contact & filters.user(user_id))(
                self.receive_contact
            )
        )

        await message.reply(
            "🔐 **Authorization Required**\n\n"
            "To use this bot, I need to access your Telegram account. "
            "Please share your contact information by clicking the button below.\n\n"
            "⚠️ **Privacy Note**: Your phone number will only be used for authentication.",
            reply_markup=keyboard,
        )

    async def after_receive_contact(self, client: Client, message):
        """Called after receiving contact information."""
        logger.debug("After receiving contact")
        contact = message.contact
        if contact and contact.user_id == message.from_user.id:
            self._contact_valid = True
            self.user_client.phone_number = contact.phone_number
            await self.user_client.send_code(phone_number=contact.phone_number)
            await self.ask_code(client=client, message=message)
            client.add_handler(
                client.on_message(filters.text & filters.user(contact.user_id))(
                    self.receive_code
                )
            )
        else:
            self._contact_valid = False
            await self.handle_invalid_contact(client=client, message=message)

    async def after_ask_code(self, client: Client, message):
        """Called after asking for verification code."""
        logger.debug("After asking for code")
        await message.reply("Please enter the verification code sent to your phone.")

    async def after_handle_invalid_contact(self, client: Client, message):
        """Called after handling invalid contact."""
        logger.debug("After handling invalid contact")
        await message.reply("Invalid contact. Please share your contact information.")

    async def after_receive_code(self, client: Client, message):
        """Called after receiving verification code."""
        logger.debug("After receiving code")
        await self.user_client.sign_in(code=message.text)
        await message.reply("You have been successfully authorized!")

    async def after_finalize(self, *args, **kwargs):
        """Called after finalizing authorization."""
        logger.debug("After finalizing authorization")

    async def after_unhandled(self, *args, **kwargs):
        """Called after handling unhandled authorization state."""
        logger.debug("After handling unhandled state")
