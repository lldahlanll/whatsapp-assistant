"""MockMessagingGateway for testing."""

from typing import Any

from whatsapp_platform.application.interfaces.messaging_gateway import (
    EventHandler,
    IMessagingGateway,
)
from whatsapp_platform.domain.events.base import DomainEvent
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import MediaContent


class MockMessagingGateway(IMessagingGateway):
    def __init__(self) -> None:
        self._connected = False
        self._sent_texts: list[tuple] = []
        self._sent_media: list[tuple] = []
        self._sent_presence: list[tuple] = []
        self._listeners: dict[type[DomainEvent], list[EventHandler]] = {}
        self._event_bus = None

    def set_event_bus(self, event_bus) -> None:  # type: ignore[override]
        self._event_bus = event_bus

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def send_text(self, to: JID, text: str, quoted: Any | None = None) -> str:
        self._sent_texts.append((to, text, quoted))
        return f"mock-msg-{len(self._sent_texts)}"

    async def send_chat_presence(self, to: JID, composing: bool) -> None:
        self._sent_presence.append((to, composing))

    async def send_media(
        self, to: JID, media: MediaContent, caption: str | None = None
    ) -> str:
        self._sent_media.append((to, media, caption))
        return f"mock-media-{len(self._sent_media)}"

    async def download_media(self, raw_message: Any) -> bytes:
        return b"mock-media-bytes-content"

    async def pair_phone(self, phone_number: str) -> str:
        return "12345678"

    def subscribe_event(self, event_type: type, handler: EventHandler) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)

    async def simulate_event(self, event: DomainEvent) -> None:
        """Used in tests to simulate incoming gateway events."""
        handlers = self._listeners.get(type(event), [])
        for h in handlers:
            await h(event)

    async def get_group_info(self, group_jid: JID) -> dict:
        return {
            "jid": str(group_jid),
            "owner": "628111@s.whatsapp.net",
            "name": "Test Group",
            "participants": ["628111@s.whatsapp.net", "628222@s.whatsapp.net"],
        }

    async def get_group_invite_link(self, group_jid: JID, revoke: bool = False) -> str:
        return f"https://chat.whatsapp.com/mock-{group_jid.user}"

    async def update_group_participants(
        self, group_jid: JID, participants: list[JID], action: str
    ) -> None:
        pass

    async def set_group_name(self, group_jid: JID, name: str) -> None:
        pass

    async def leave_group(self, group_jid: JID) -> None:
        pass
