"""IConversationRepository abstract interface."""

from abc import ABC, abstractmethod

from whatsapp_platform.domain.entities.conversation import Conversation
from whatsapp_platform.domain.value_objects.jid import JID


class IConversationRepository(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> None:
        """Persist or update a conversation record."""

    @abstractmethod
    async def get_by_jid(self, jid: JID) -> Conversation | None:
        """Retrieve a conversation by its JID."""

    @abstractmethod
    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        """List all conversations ordered by last_message_at descending."""

    @abstractmethod
    async def delete(self, jid: JID) -> None:
        """Delete a conversation record."""
