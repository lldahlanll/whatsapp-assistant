"""Pydantic schemas for message-related API endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """Request body for sending a text message."""

    to: str = Field(
        description="Recipient JID (e.g. '628123456789@s.whatsapp.net' or '120363000000@g.us' for group)",
        examples=["628123456789@s.whatsapp.net"],
    )
    text: str = Field(
        description="Message text content",
        min_length=1,
        max_length=65536,
        examples=["Hello from WhatsApp API!"],
    )


class MessageResponse(BaseModel):
    """Response schema representing a sent or stored message."""

    id: str = Field(description="Unique message ID")
    chat_jid: str = Field(description="Chat JID this message belongs to")
    sender_jid: str = Field(description="Sender's JID")
    direction: str = Field(description="Message direction: INBOUND or OUTBOUND")
    status: str = Field(description="Message status: PENDING, SENT, DELIVERED, READ, FAILED")
    text: str | None = Field(default=None, description="Text content if message is text type")
    media_type: str | None = Field(default=None, description="Media type if message is media")
    is_from_me: bool = Field(description="True if bot sent this message")
    push_name: str | None = Field(default=None, description="Sender display name")
    timestamp: datetime = Field(description="Message timestamp")


class ConversationHistoryResponse(BaseModel):
    """Paginated conversation history response."""

    chat_jid: str = Field(description="Chat JID for this conversation")
    messages: list[MessageResponse]
    total: int = Field(description="Total messages returned")
    limit: int = Field(description="Page size limit used")
    offset: int = Field(description="Page offset used")
