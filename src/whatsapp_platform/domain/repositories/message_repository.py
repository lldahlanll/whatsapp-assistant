"""IMessageRepository abstract interface."""

from abc import ABC, abstractmethod

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.value_objects.jid import JID


class IMessageRepository(ABC):
    @abstractmethod
    async def save(self, message: Message) -> None:
        pass

    @abstractmethod
    async def get_by_id(self, message_id: str) -> Message | None:
        pass

    @abstractmethod
    async def get_chat_messages(
        self, chat_jid: JID, limit: int = 50, offset: int = 0
    ) -> list[Message]:
        pass
