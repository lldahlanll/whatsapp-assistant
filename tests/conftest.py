"""Shared Pytest fixtures."""

import pytest_asyncio

from whatsapp_platform.infrastructure.database.base import (
    Base,
    create_engine_and_session_factory,
)


@pytest_asyncio.fixture
async def async_db_session_factory():
    engine, session_factory = create_engine_and_session_factory(
        "sqlite+aiosqlite:///:memory:"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory
    await engine.dispose()
