"""IMessagingGateway interface contract for WhatsApp integration (Neonize adapter)."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import MediaContent

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class IMessagingGateway(ABC):
    @abstractmethod
    def set_event_bus(self, event_bus: Any) -> None:
        """Inject the application IEventBus to forward domain events."""

    @abstractmethod
    async def connect(self) -> None:
        """Start connection to WhatsApp gateway."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from WhatsApp gateway."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if active connection exists."""

    @abstractmethod
    async def send_text(self, to: JID, text: str, quoted: Any | None = None) -> str:
        """Send plain text message (optionally quoting a message) and return message ID."""

    @abstractmethod
    async def send_chat_presence(self, to: JID, composing: bool) -> None:
        """Send chat presence status (typing indicator ON if composing=True, OFF if composing=False)."""

    @abstractmethod
    async def send_media(
        self, to: JID, media: MediaContent, caption: str | None = None
    ) -> str:
        """Send media message (image, audio, document, video) and return message ID."""

    @abstractmethod
    async def download_media(self, raw_message: Any) -> bytes:
        """Download raw media bytes from a message object."""

    @abstractmethod
    async def pair_phone(self, phone_number: str) -> str:
        """Request 8-digit pairing code for target phone number."""

    @abstractmethod
    def subscribe_event(self, event_type: type, handler: EventHandler) -> None:
        """Subscribe internal event handler."""

    @abstractmethod
    async def get_group_info(self, group_jid: JID) -> dict:
        """Fetch group metadata and info."""

    @abstractmethod
    async def get_group_invite_link(self, group_jid: JID, revoke: bool = False) -> str:
        """Fetch or revoke group invite link."""

    @abstractmethod
    async def update_group_participants(
        self, group_jid: JID, participants: list[JID], action: str
    ) -> None:
        """Update group participants (action: 'add', 'remove', 'promote', 'demote')."""

    @abstractmethod
    async def set_group_name(self, group_jid: JID, name: str) -> None:
        """Set group subject/name."""

    @abstractmethod
    async def leave_group(self, group_jid: JID) -> None:
        """Leave target WhatsApp group."""
