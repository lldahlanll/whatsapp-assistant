"""ISessionRepository abstract interface."""

from abc import ABC, abstractmethod

from whatsapp_platform.domain.entities.session import WhatsAppSession


class ISessionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, session_id: str) -> WhatsAppSession | None:
        pass

    @abstractmethod
    async def save(self, session: WhatsAppSession) -> None:
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        pass
