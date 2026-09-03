"""Shared fixtures for API tests.

Provides a FastAPI TestClient pre-wired with mock use cases
and mock dependencies so tests don't hit real WhatsApp or DB.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.mocks.mock_event_bus import MockEventBus
from tests.mocks.mock_gateway import MockMessagingGateway
from whatsapp_platform.application.use_cases.get_conversation import GetConversationHistoryUseCase
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.database.base import (
    Base,
    create_engine_and_session_factory,
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
from whatsapp_platform.presentation.api.app import create_api_app


class MockContainer:
    """Minimal in-memory container for API testing — no Neonize, no Alembic."""

    def __init__(self, settings: Settings, session_factory) -> None:
        self._services: dict = {}
        self.settings = settings
        gateway = MockMessagingGateway()
        event_bus = MockEventBus()
        message_repo = SQLAlchemyMessageRepository(session_factory)
        session_repo = SQLAlchemySessionRepository(session_factory)
        conversation_repo = SQLAlchemyConversationRepository(session_factory)

        from whatsapp_platform.application.interfaces.event_bus import IEventBus
        from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
        from whatsapp_platform.domain.repositories.conversation_repository import IConversationRepository
        from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
        from whatsapp_platform.domain.repositories.session_repository import ISessionRepository

        self._services = {
            Settings: settings,
            ISessionRepository: session_repo,
            IMessageRepository: message_repo,
            IConversationRepository: conversation_repo,
            IMessagingGateway: gateway,
            IEventBus: event_bus,
            SendMessageUseCase: SendMessageUseCase(gateway, message_repo, event_bus),
            GetConversationHistoryUseCase: GetConversationHistoryUseCase(message_repo),
            ManageSessionUseCase: ManageSessionUseCase(gateway, session_repo),
            GroupManagementUseCase: GroupManagementUseCase(gateway),
        }

    def resolve(self, interface):
        if interface not in self._services:
            raise KeyError(f"Service '{interface}' not registered")
        return self._services[interface]


@pytest_asyncio.fixture
async def api_client():
    """Async HTTP client for testing the FastAPI app with mocked container."""
    # In-memory SQLite for tests
    engine, session_factory = create_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(
        app_name="whatsapp-platform-test",
        app_env="development",
        debug=True,
        session_name="test-session",
        database_url="sqlite+aiosqlite:///:memory:",
        api_key="",  # Auth disabled for tests
    )

    container = MockContainer(settings, session_factory)
    app = create_api_app(container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest_asyncio.fixture
async def api_client_with_key():
    """Async HTTP client for testing API key authentication."""
    engine, session_factory = create_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(
        app_name="whatsapp-platform-test",
        app_env="development",
        debug=True,
        session_name="test-session",
        database_url="sqlite+aiosqlite:///:memory:",
        api_key="test-secret-key",
    )

    container = MockContainer(settings, session_factory)
    app = create_api_app(container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await engine.dispose()
