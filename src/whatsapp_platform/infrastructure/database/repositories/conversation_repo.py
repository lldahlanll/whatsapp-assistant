"""SQLAlchemy Conversation Repository implementation."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from whatsapp_platform.domain.entities.conversation import Conversation
from whatsapp_platform.domain.repositories.conversation_repository import (
    IConversationRepository,
)
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.infrastructure.database.models import ConversationModel


class SQLAlchemyConversationRepository(IConversationRepository):
    """Persist Conversation aggregates to the whatsapp_conversations table."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def save(self, conversation: Conversation) -> None:
        """Upsert a conversation record using a single atomic SQL statement.

        Using SQLite's ``INSERT ... ON CONFLICT(jid) DO UPDATE`` instead of a
        read-then-write approach eliminates the race condition that caused
        ``UNIQUE constraint failed`` when two messages from the same chat
        arrived concurrently (both reads returned None, both tried to INSERT).
        """
        jid_str = str(conversation.chat_jid)
        last_msg_at = (
            conversation.last_message.timestamp
            if conversation.last_message
            else conversation.updated_at
        )

        stmt = (
            sqlite_insert(ConversationModel)
            .values(
                jid=jid_str,
                display_name=None,
                unread_count=conversation.unread_count,
                is_group=conversation.chat_jid.is_group,
                last_message_at=last_msg_at,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["jid"],
                set_={
                    "unread_count": conversation.unread_count,
                    "is_group": conversation.chat_jid.is_group,
                    "last_message_at": last_msg_at,
                },
            )
        )

        async with self.session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def get_by_jid(self, jid: JID) -> Conversation | None:
        """Retrieve a conversation by JID. Returns a lightweight Conversation (no messages loaded)."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.jid == str(jid))
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        """List conversations ordered by most recently active."""
        async with self.session_factory() as session:
            stmt = (
                select(ConversationModel)
                .order_by(ConversationModel.last_message_at.desc().nulls_last())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_entity(m) for m in models]

    async def delete(self, jid: JID) -> None:
        """Delete a conversation record."""
        async with self.session_factory() as session:
            model = await session.get(ConversationModel, str(jid))
            if model:
                await session.delete(model)
                await session.commit()

    def _to_entity(self, model: ConversationModel) -> Conversation:
        """Map ORM model → domain entity (lightweight, no messages loaded)."""
        return Conversation(
            chat_jid=JID.parse(model.jid),
            unread_count=model.unread_count,
            last_message=None,  # Messages are loaded on demand via IMessageRepository
            messages=[],
            updated_at=model.last_message_at or model.created_at,
        )
