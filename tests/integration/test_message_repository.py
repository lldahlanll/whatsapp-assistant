"""Integration tests for SQLAlchemy Message Repository."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.database.base import (
    Base,
    create_engine_and_session_factory,
)
from whatsapp_platform.infrastructure.database.repositories.message_repo import (
    SQLAlchemyMessageRepository,
)


@pytest_asyncio.fixture
async def session_factory():
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


def _make_message(msg_id: str, text: str) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse("628111111@s.whatsapp.net"),
        sender_jid=JID.parse("628222222@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_save_and_retrieve_message(session_factory):
    repo = SQLAlchemyMessageRepository(session_factory)
    msg = _make_message("msg-001", "Hello Integration!")
    await repo.save(msg)

    retrieved = await repo.get_by_id("msg-001")
    assert retrieved is not None
    assert retrieved.id == "msg-001"
    assert isinstance(retrieved.content, TextContent)
    assert retrieved.content.text == "Hello Integration!"


@pytest.mark.asyncio
async def test_get_chat_messages_ordered(session_factory):
    repo = SQLAlchemyMessageRepository(session_factory)
    for i in range(5):
        await repo.save(_make_message(f"msg-{i:03}", f"Message {i}"))

    chat_jid = JID.parse("628111111@s.whatsapp.net")
    messages = await repo.get_chat_messages(chat_jid, limit=3)
    assert len(messages) == 3
