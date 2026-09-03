"""Conversation aggregate root entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.value_objects.jid import JID


@dataclass
class Conversation:
    chat_jid: JID
    unread_count: int = 0
    last_message: Message | None = None
    messages: list[Message] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.last_message = message
        self.updated_at = message.timestamp
        if not message.is_from_me:
            self.unread_count += 1

    def mark_as_read(self) -> None:
        self.unread_count = 0
