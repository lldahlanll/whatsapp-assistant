"""IContactRepository abstract interface."""

from abc import ABC, abstractmethod

from whatsapp_platform.domain.entities.contact import Contact
from whatsapp_platform.domain.value_objects.jid import JID


class IContactRepository(ABC):
    @abstractmethod
    async def save(self, contact: Contact) -> None:
        pass

    @abstractmethod
    async def get_by_jid(self, jid: JID) -> Contact | None:
        pass
