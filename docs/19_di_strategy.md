# DOC-019 · Dependency Injection Strategy

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Python Engineer  

---

## 1. Filosofi DI di Project Ini

**Prinsip Utama:**  
> "Jangan instantiate dependencies di dalam class. Terima mereka dari luar."

**Mengapa DI?**
1. **Testability**: Mudah inject mock dalam test
2. **Flexibility**: Ganti implementasi tanpa ubah consumer
3. **Explicitness**: Dependencies setiap class terlihat jelas di constructor

**Pilihan untuk MVP:** Manual DI dengan `container.py` sebagai pusat konfigurasi.

---

## 2. Pola Constructor Injection

```python
# BENAR — constructor injection
class SendMessageUseCase:
    def __init__(
        self,
        gateway: IMessagingGateway,
        message_repo: IMessageRepository,
        event_bus: IEventBus,
    ) -> None:
        self._gateway = gateway
        self._message_repo = message_repo
        self._event_bus = event_bus

# SALAH — instantiate di dalam class
class SendMessageUseCase:
    def __init__(self) -> None:
        self._gateway = NeonizeGateway()  # Hard coupling! Tidak bisa di-mock
        self._message_repo = SQLAlchemyMessageRepository()  # Butuh DB!
```

---

## 3. Container (`container.py`)

```python
# src/whatsapp_platform/container.py

from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.database.base import create_async_engine, AsyncSessionFactory
from whatsapp_platform.infrastructure.neonize.gateway import NeonizeGateway
from whatsapp_platform.infrastructure.database.repositories.session_repo import SQLAlchemySessionRepository
from whatsapp_platform.infrastructure.database.repositories.message_repo import SQLAlchemyMessageRepository
from whatsapp_platform.infrastructure.database.repositories.contact_repo import SQLAlchemyContactRepository
from whatsapp_platform.application.services.event_bus import InMemoryEventBus
from whatsapp_platform.application.services.feature_registry import FeatureRegistry
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.application.use_cases.manage_session import SessionManagementUseCase
from whatsapp_platform.features.session import SessionFeature
from whatsapp_platform.features.messaging import MessagingFeature
from whatsapp_platform.features.commands import CommandsFeature
from whatsapp_platform.features.commands.registry import CommandHandlerRegistry

@dataclass
class Container:
    """
    Dependency Injection Container.
    
    Semua dependencies di-wire di sini.
    Gunakan @cached_property untuk singletons.
    Buat method baru untuk transient instances.
    """
    
    settings: Settings
    
    # =========================================================================
    # INFRASTRUCTURE — Singletons
    # =========================================================================
    
    @cached_property
    def db_engine(self):
        return create_async_engine(str(self.settings.database_url.get_secret_value()))
    
    @cached_property
    def session_factory(self) -> AsyncSessionFactory:
        return AsyncSessionFactory(bind=self.db_engine)
    
    @cached_property
    def event_bus(self) -> InMemoryEventBus:
        return InMemoryEventBus()
    
    @cached_property
    def messaging_gateway(self) -> NeonizeGateway:
        return NeonizeGateway(
            session_db_url=self.settings.neonize_session_db,
            event_bus=self.event_bus,
        )
    
    # =========================================================================
    # REPOSITORIES — Singletons (share session factory)
    # =========================================================================
    
    @cached_property
    def session_repository(self) -> SQLAlchemySessionRepository:
        return SQLAlchemySessionRepository(session_factory=self.session_factory)
    
    @cached_property
    def message_repository(self) -> SQLAlchemyMessageRepository:
        return SQLAlchemyMessageRepository(session_factory=self.session_factory)
    
    @cached_property
    def contact_repository(self) -> SQLAlchemyContactRepository:
        return SQLAlchemyContactRepository(session_factory=self.session_factory)
    
    # =========================================================================
    # USE CASES — Transient (new instance per call, kecuali state-heavy)
    # =========================================================================
    
    def make_send_message_use_case(self) -> SendMessageUseCase:
        """Factory method — transient instance."""
        return SendMessageUseCase(
            gateway=self.messaging_gateway,
            message_repo=self.message_repository,
            event_bus=self.event_bus,
        )
    
    @cached_property
    def session_management_use_case(self) -> SessionManagementUseCase:
        """Singleton — karena manage stateful session."""
        return SessionManagementUseCase(
            session_repo=self.session_repository,
            event_bus=self.event_bus,
        )
    
    # =========================================================================
    # FEATURES
    # =========================================================================
    
    @cached_property
    def command_handler_registry(self) -> CommandHandlerRegistry:
        return CommandHandlerRegistry()
    
    @cached_property
    def feature_registry(self) -> FeatureRegistry:
        registry = FeatureRegistry(event_bus=self.event_bus)
        
        # Register semua feature modules
        registry.register(SessionFeature(
            session_use_case=self.session_management_use_case,
            settings=self.settings,
        ))
        
        registry.register(MessagingFeature(
            sender=self.messaging_gateway,
            message_repo=self.message_repository,
        ))
        
        registry.register(CommandsFeature(
            command_registry=self.command_handler_registry,
            send_use_case_factory=self.make_send_message_use_case,
        ))
        
        # Conditional feature — hanya jika AI enabled
        if self.settings.ai_provider != "none":
            from whatsapp_platform.features.ai_integration import AIIntegrationFeature
            from whatsapp_platform.features.ai_integration.providers import create_provider
            
            registry.register(AIIntegrationFeature(
                ai_provider=create_provider(self.settings),
                send_use_case_factory=self.make_send_message_use_case,
                message_repo=self.message_repository,
                command_registry=self.command_handler_registry,
            ))
        
        return registry


def build_container(settings: Settings | None = None) -> Container:
    """Factory function untuk membuat container."""
    if settings is None:
        settings = Settings()
    return Container(settings=settings)
```

---

## 4. Scope Management

| Scope | Implementasi | Kapan Digunakan |
|-------|-------------|-----------------|
| **Singleton** | `@cached_property` pada Container | Gateway, repositories, event bus, registries |
| **Transient** | `make_*()` factory methods | Use cases yang ringan, stateless |
| **Scoped** | Pass session ke repository | SQLAlchemy session (satu per request/transaction) |

---

## 5. DI untuk Testing

```python
# tests/conftest.py

import pytest
from whatsapp_platform.container import Container
from whatsapp_platform.infrastructure.config.settings import Settings
from tests.mocks import MockMessagingGateway, MockEventBus

@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        neonize_session_db="sqlite:///:memory:",
        environment="testing",
        ai_provider="none",
    )

@pytest.fixture
def mock_gateway() -> MockMessagingGateway:
    return MockMessagingGateway()

@pytest.fixture
def mock_event_bus() -> MockEventBus:
    return MockEventBus()

@pytest.fixture
def send_message_use_case(mock_gateway, mock_event_bus, message_repo):
    """Use case dengan semua dependencies di-mock."""
    return SendMessageUseCase(
        gateway=mock_gateway,
        message_repo=message_repo,
        event_bus=mock_event_bus,
    )
```

---

## 6. MockMessagingGateway (untuk Testing)

```python
# tests/mocks/mock_gateway.py

from whatsapp_platform.domain.value_objects import JID, MessageID
from whatsapp_platform.application.interfaces import IMessagingGateway

class MockMessagingGateway:
    """
    Test double untuk IMessagingGateway.
    Tidak melakukan network call — hanya record calls untuk assertion.
    """
    
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.sent_messages: list[tuple[JID, str]] = []
        self.sent_media: list[tuple[JID, bytes]] = []
        self._call_count: dict[str, int] = {}
    
    async def send_text(self, to: JID, body: str) -> MessageID:
        self.sent_messages.append((to, body))
        self._call_count["send_text"] = self._call_count.get("send_text", 0) + 1
        return f"mock-msg-{len(self.sent_messages):04d}"
    
    async def send_image(self, to: JID, image_data: bytes, **kwargs) -> MessageID:
        self.sent_media.append((to, image_data))
        return f"mock-media-{len(self.sent_media):04d}"
    
    async def start(self) -> None:
        self._connected = True
    
    async def stop(self) -> None:
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    # Assertion helpers
    def assert_sent_to(self, jid: JID, body: str) -> None:
        assert (jid, body) in self.sent_messages, \
            f"Expected message to {jid} with body '{body}' not found"
    
    def assert_call_count(self, method: str, expected: int) -> None:
        actual = self._call_count.get(method, 0)
        assert actual == expected, f"Expected {expected} calls to {method}, got {actual}"
```

---

## 7. IContainer Interface (untuk Feature Modules)

```python
# src/application/interfaces/container.py

from typing import Protocol, TypeVar

T = TypeVar("T")

class IContainer(Protocol):
    """
    Minimal interface yang diekspos ke feature modules.
    Feature modules hanya butuh resolve dependencies, tidak perlu akses ke Container penuh.
    """
    
    def resolve(self, service_type: type[T]) -> T:
        """Resolve dependency berdasarkan type."""
        ...
```

---

## References

- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-013: API Contract](./13_api_contract.md)
- [DOC-017: Project Structure](./17_project_structure.md)
- [DOC-020: Testing Strategy](./18_testing_strategy.md)
