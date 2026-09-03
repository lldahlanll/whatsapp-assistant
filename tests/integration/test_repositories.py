"""Integration tests for SQLAlchemy Repositories (Session, Message, Contact, Conversation).

Uses an in-memory SQLite database initialized with Base.metadata.create_all for fast, isolated integration testing.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.contact import Contact
from whatsapp_platform.domain.entities.conversation import Conversation
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.entities.session import WhatsAppSession
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.domain.value_objects.session_status import SessionStatus
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.contact_repo import (
    SQLAlchemyContactRepository,
)
from whatsapp_platform.infrastructure.database.repositories.conversation_repo import (
    SQLAlchemyConversationRepository,
)
from whatsapp_platform.infrastructure.database.repositories.message_repo import (
    SQLAlchemyMessageRepository,
)
from whatsapp_platform.infrastructure.database.repositories.session_repo import (
    SQLAlchemySessionRepository,
)


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Session Repository Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_repository_save_and_get(async_session_factory):
    repo = SQLAlchemySessionRepository(async_session_factory)

    session = WhatsAppSession(
        id="test_session_1",
        phone_number="628123456789",
        status=SessionStatus.CONNECTED,
    )

    await repo.save(session)

    fetched = await repo.get_by_id("test_session_1")
    assert fetched is not None
    assert fetched.id == "test_session_1"
    assert fetched.phone_number == "628123456789"
    assert fetched.status == SessionStatus.CONNECTED


@pytest.mark.asyncio
async def test_session_repository_delete(async_session_factory):
    repo = SQLAlchemySessionRepository(async_session_factory)

    session = WhatsAppSession(id="session_to_delete")
    await repo.save(session)

    await repo.delete("session_to_delete")
    fetched = await repo.get_by_id("session_to_delete")
    assert fetched is None


# ---------------------------------------------------------------------------
# Message Repository Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_repository_save_and_get_chat_messages(async_session_factory):
    repo = SQLAlchemyMessageRepository(async_session_factory)

    chat_jid = JID.parse("628123456789@s.whatsapp.net")
    sender_jid = JID.parse("628987654321@s.whatsapp.net")

    msg1 = Message(
        id="msg-db-1",
        chat_jid=chat_jid,
        sender_jid=sender_jid,
        content=TextContent(text="First message"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
    )
    msg2 = Message(
        id="msg-db-2",
        chat_jid=chat_jid,
        sender_jid=sender_jid,
        content=TextContent(text="Second message"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.READ,
        timestamp=datetime.now(UTC),
    )

    await repo.save(msg1)
    await repo.save(msg2)

    fetched_msg = await repo.get_by_id("msg-db-1")
    assert fetched_msg is not None
    assert fetched_msg.id == "msg-db-1"
    assert fetched_msg.content.text == "First message"

    chat_msgs = await repo.get_chat_messages(chat_jid)
    assert len(chat_msgs) == 2


# ---------------------------------------------------------------------------
# Contact Repository Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_repository_save_and_get(async_session_factory):
    repo = SQLAlchemyContactRepository(async_session_factory)

    jid = JID.parse("628111222333@s.whatsapp.net")
    contact = Contact(
        jid=jid,
        name="John Doe",
        push_name="Johnny",
        is_business=True,
    )

    await repo.save(contact)

    fetched = await repo.get_by_jid(jid)
    assert fetched is not None
    assert fetched.name == "John Doe"
    assert fetched.push_name == "Johnny"
    assert fetched.is_business is True


# ---------------------------------------------------------------------------
# Conversation Repository Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_repository_save_and_list_all(async_session_factory):
    repo = SQLAlchemyConversationRepository(async_session_factory)

    chat_jid1 = JID.parse("628111@s.whatsapp.net")
    chat_jid2 = JID.parse("123456789@g.us")

    conv1 = Conversation(chat_jid=chat_jid1, unread_count=2)
    conv2 = Conversation(chat_jid=chat_jid2, unread_count=0)

    await repo.save(conv1)
    await repo.save(conv2)

    fetched_conv1 = await repo.get_by_jid(chat_jid1)
    assert fetched_conv1 is not None
    assert fetched_conv1.unread_count == 2

    all_convs = await repo.list_all()
    assert len(all_convs) == 2

    await repo.delete(chat_jid1)
    fetched_after_delete = await repo.get_by_jid(chat_jid1)
    assert fetched_after_delete is None
