"""Integration tests for SQLAlchemy Session Repository."""

import pytest
import pytest_asyncio

from whatsapp_platform.domain.entities.session import WhatsAppSession
from whatsapp_platform.domain.value_objects.session_status import SessionStatus
from whatsapp_platform.infrastructure.database.base import (
    Base,
    create_engine_and_session_factory,
)
from whatsapp_platform.infrastructure.database.repositories.session_repo import (
    SQLAlchemySessionRepository,
)


@pytest_asyncio.fixture
async def session_factory():
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_and_retrieve_session(session_factory):
    repo = SQLAlchemySessionRepository(session_factory)
    session = WhatsAppSession(id="sess-test-001", phone_number="628123456789")
    session.connect()

    await repo.save(session)

    retrieved = await repo.get_by_id("sess-test-001")
    assert retrieved is not None
    assert retrieved.id == "sess-test-001"
    assert retrieved.phone_number == "628123456789"
    assert retrieved.status == SessionStatus.CONNECTED


@pytest.mark.asyncio
async def test_get_missing_session_returns_none(session_factory):
    repo = SQLAlchemySessionRepository(session_factory)
    result = await repo.get_by_id("non-existent-session")
    assert result is None


@pytest.mark.asyncio
async def test_delete_session(session_factory):
    repo = SQLAlchemySessionRepository(session_factory)
    session = WhatsAppSession(id="sess-delete-001")
    await repo.save(session)

    before = await repo.get_by_id("sess-delete-001")
    assert before is not None

    await repo.delete("sess-delete-001")
    after = await repo.get_by_id("sess-delete-001")
    assert after is None
