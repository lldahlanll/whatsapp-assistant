"""OutgoingMessageDTO — data transfer object for outbound WhatsApp messages."""

from dataclasses import dataclass


@dataclass
class OutgoingMessageDTO:
    """Represents an outbound message to be sent via WhatsApp.

    This DTO is the input contract for SendMessageUseCase and SendMediaUseCase.
    """

    target_jid: str
    text_content: str | None = None

    # Media fields
    media_path: str | None = None
    media_type: str = "TEXT"
    media_mime_type: str | None = None
    caption: str | None = None

    # Reply / quote context
    reply_to_id: str | None = None
    quoted_text: str | None = None
    quoted_sender_jid: str | None = None
