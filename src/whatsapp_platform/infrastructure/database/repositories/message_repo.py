"""SQLAlchemy Message Repository implementation."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.database.models import MessageModel


class SQLAlchemyMessageRepository(IMessageRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def save(self, message: Message) -> None:
        async with self.session_factory() as session:
            text_val = None
            media_type_val = "TEXT"

            if isinstance(message.content, TextContent):
                text_val = message.content.text
            elif isinstance(message.content, MediaContent):
                text_val = message.content.caption or message.content.file_path
                media_type_val = message.content.media_type.value

            values = dict(
                id=message.id,
                chat_jid=str(message.chat_jid),
                sender_jid=str(message.sender_jid),
                text_content=text_val,
                media_type=media_type_val,
                direction=message.direction.value,
                status=message.status.value,
                timestamp=message.timestamp,
                push_name=message.push_name,
                is_from_me=message.is_from_me,
            )

            # Atomic upsert — avoids race condition between concurrent coroutines
            # that would each see "not exists" and both try to INSERT.
            stmt = (
                sqlite_insert(MessageModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[MessageModel.id],
                    set_={
                        k: v for k, v in values.items() if k != "id"
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_by_id(self, message_id: str) -> Message | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(MessageModel).where(MessageModel.id == message_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    async def get_chat_messages(
        self, chat_jid: JID, limit: int = 50, offset: int = 0
    ) -> list[Message]:
        async with self.session_factory() as session:
            stmt = (
                select(MessageModel)
                .where(MessageModel.chat_jid == str(chat_jid))
                .order_by(MessageModel.timestamp.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_entity(m) for m in models]

    def _to_entity(self, model: MessageModel) -> Message:
        content: TextContent | MediaContent
        if model.media_type == "TEXT":
            content = TextContent(text=model.text_content or "")
        else:
            content = MediaContent(
                media_type=MediaType(model.media_type),
                caption=model.text_content,
            )

        return Message(
            id=model.id,
            chat_jid=JID.parse(model.chat_jid),
            sender_jid=JID.parse(model.sender_jid),
            content=content,
            direction=MessageDirection(model.direction),
            status=MessageStatus(model.status),
            timestamp=model.timestamp,
            push_name=model.push_name,
            is_from_me=model.is_from_me,
        )
