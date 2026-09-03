"""SQLAlchemy implementation of IContactRepository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from whatsapp_platform.domain.entities.contact import Contact
from whatsapp_platform.domain.repositories.contact_repository import IContactRepository
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.infrastructure.database.models import ContactModel


class SQLAlchemyContactRepository(IContactRepository):
    """Async SQLAlchemy implementation of IContactRepository using merge-based upsert."""
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def save(self, contact: Contact) -> None:
        async with self.session_factory() as session:
            model = ContactModel(
                jid=str(contact.jid),
                name=contact.name,
                push_name=contact.push_name,
                is_business=contact.is_business,
            )
            await session.merge(model)
            await session.commit()

    async def get_by_jid(self, jid: JID) -> Contact | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ContactModel).where(ContactModel.jid == str(jid))
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return Contact(
                jid=JID.parse(model.jid),
                name=model.name,
                push_name=model.push_name,
                is_business=model.is_business,
            )
