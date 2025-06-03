
from pydantic import BaseModel, Field


class Intent(BaseModel):
    intent: str = Field(
        ...,
        description=f"The intent of the user input. Must be one of the predefined values:"
        "SUMMARY - trigger this for summarizing chats;"
        "MARK_AS_READ - trigger this when the user wants to mark a chat or chats as read;"
        "ANALYZE - trigger this for requests that involve analyzing a chat;"
        "OTHER - trigger this for any other type of request that does not fit into the above categories.",
    )
    chat_name: str | None = Field(
        None,
        description="The name of the chat to be used for summarization or analysis. "
        "This is optional and can be used to specify a particular chat if needed.",
    )