"""Messaging domain events."""

from dataclasses import dataclass
from typing import Any

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.events.base import DomainEvent


@dataclass
class MessageReceived(DomainEvent):
    message: Message | None = None
    raw_message: Any | None = None


@dataclass
class MessageSent(DomainEvent):
    message: Message | None = None


@dataclass
class MessageStatusUpdated(DomainEvent):
    message_id: str = ""
    chat_jid_str: str = ""
    new_status: str = ""
