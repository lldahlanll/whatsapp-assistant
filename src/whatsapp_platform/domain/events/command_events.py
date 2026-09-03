"""Command domain events."""

from dataclasses import dataclass

from whatsapp_platform.domain.events.base import DomainEvent
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID


@dataclass
class CommandExecuted(DomainEvent):
    command: BotCommand | None = None
    chat_jid: JID | None = None
    sender_jid: JID | None = None
    handler_name: str = ""


@dataclass
class UnknownCommandReceived(DomainEvent):
    raw_command: str = ""
    chat_jid: JID | None = None
    sender_jid: JID | None = None
