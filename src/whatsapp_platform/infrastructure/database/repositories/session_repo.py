"""SQLAlchemy Session Repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from whatsapp_platform.domain.entities.session import WhatsAppSession
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository
from whatsapp_platform.domain.value_objects.session_status import SessionStatus
from whatsapp_platform.infrastructure.database.models import SessionModel


class SQLAlchemySessionRepository(ISessionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_by_id(self, session_id: str) -> WhatsAppSession | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return WhatsAppSession(
                id=model.id,
                phone_number=model.phone_number,
                status=SessionStatus(model.status),
                created_at=model.created_at,
                last_connected_at=model.last_connected_at,
                reconnect_attempts=model.reconnect_attempts,
            )

    async def save(self, session_obj: WhatsAppSession) -> None:
        async with self.session_factory() as session:
            model = await session.get(SessionModel, session_obj.id)
            if not model:
                model = SessionModel(id=session_obj.id)
                session.add(model)

            model.phone_number = session_obj.phone_number
            model.status = session_obj.status.value
            model.last_connected_at = session_obj.last_connected_at
            model.reconnect_attempts = session_obj.reconnect_attempts
            await session.commit()

    async def delete(self, session_id: str) -> None:
        async with self.session_factory() as session:
            model = await session.get(SessionModel, session_id)
            if model:
                await session.delete(model)
                await session.commit()
