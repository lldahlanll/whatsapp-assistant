"""IncomingMessageDTO — data transfer object for inbound WhatsApp messages."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IncomingMessageDTO:
    """Represents an inbound message received from WhatsApp.

    This DTO is the boundary object between the infrastructure layer
    (Neonize event mapper) and the application use cases.
    """

    message_id: str
    chat_jid: str
    sender_jid: str
    text_content: str | None
    media_type: str
    timestamp: datetime

    # Sender context
    push_name: str | None = None
    is_from_me: bool = False
    is_group: bool = False

    # Reply / quote context
    reply_to_id: str | None = None
    quoted_sender_jid: str | None = None
    quoted_text: str | None = None

    # Mentions
    mentioned_jids: list[str] = field(default_factory=list)

    # Media metadata (populated when media_type != TEXT)
    media_url: str | None = None
    media_mime_type: str | None = None
    media_file_name: str | None = None
    media_file_size: int | None = None
