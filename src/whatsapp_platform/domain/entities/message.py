"""Message entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import MessageContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus


class MessageDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


@dataclass
class Message:
    id: str
    chat_jid: JID
    sender_jid: JID
    content: MessageContent
    direction: MessageDirection
    status: MessageStatus = MessageStatus.PENDING
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    push_name: str | None = None
    is_from_me: bool = False
    reply_to_id: str | None = None
    quoted_sender_jid: JID | None = None
    mentioned_jids: list[JID] = field(default_factory=list)
    raw_message: Any | None = field(default=None, repr=False)

    def mark_sent(self) -> None:
        self.status = MessageStatus.SENT

    def mark_delivered(self) -> None:
        self.status = MessageStatus.DELIVERED

    def mark_read(self) -> None:
        self.status = MessageStatus.READ

    def mark_failed(self) -> None:
        self.status = MessageStatus.FAILED
