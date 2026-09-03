# DOC-017 · Project Structure & Codebase Layout

> **Status:** Implemented  
> **Version:** 1.1.0  
> **Last Updated:** 2026-08-07  
> **Owner:** Senior Developer  

---

## 1. Struktur Lengkap

```
whatsapp-platform/
│
├── 📁 src/                                  # Source code utama
│   └── 📁 whatsapp_platform/               # Package utama (src layout)
│       │
│       ├── 📄 __init__.py                   # Package metadata, version
│       ├── 📄 __main__.py                   # Entry point: python -m whatsapp_platform
│       ├── 📄 app.py                        # Application lifecycle (startup/shutdown)
│       ├── 📄 container.py                  # Dependency Injection Container
│       │
│       ├── 📁 domain/                       # INNER LAYER — pure Python, no deps
│       │   ├── 📄 __init__.py
│       │   ├── 📁 entities/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 session.py            # WhatsAppSession entity
│       │   │   ├── 📄 message.py            # Message entity
│       │   │   ├── 📄 contact.py            # Contact entity
│       │   │   └── 📄 conversation.py       # Conversation entity
│       │   │
│       │   ├── 📁 value_objects/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 jid.py               # JID value object
│       │   │   ├── 📄 message_id.py        # MessageID type alias
│       │   │   ├── 📄 message_status.py    # MessageStatus enum
│       │   │   ├── 📄 session_status.py    # SessionStatus enum
│       │   │   ├── 📄 bot_command.py       # BotCommand value object
│       │   │   └── 📄 message_content.py   # TextContent, MediaContent
│       │   │
│       │   ├── 📁 events/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 base.py              # DomainEvent base class
│       │   │   ├── 📄 session_events.py    # QRCodeGenerated, SessionConnected, etc.
│       │   │   ├── 📄 messaging_events.py  # MessageReceived, MessageSent, etc.
│       │   │   └── 📄 command_events.py    # CommandExecuted, UnknownCommandReceived
│       │   │
│       │   ├── 📁 repositories/            # Interfaces ONLY (Abstract)
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 session_repository.py    # ISessionRepository
│       │   │   ├── 📄 message_repository.py    # IMessageRepository
│       │   │   ├── 📄 contact_repository.py    # IContactRepository
│       │   │   └── 📄 conversation_repository.py
│       │   │
│       │   ├── 📁 services/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 command_parser.py    # CommandParserService
│       │   │   └── 📄 message_normalizer.py
│       │   │
│       │   └── 📁 exceptions/
│       │       ├── 📄 __init__.py
│       │       └── 📄 exceptions.py        # Full exception hierarchy
│       │
│       ├── 📁 application/                  # MIDDLE LAYER — orchestration
│       │   ├── 📄 __init__.py
│       │   │
│       │   ├── 📁 interfaces/              # Contracts untuk infrastructure
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 messaging_gateway.py  # IMessagingGateway
│       │   │   ├── 📄 event_bus.py          # IEventBus
│       │   │   ├── 📄 feature_module.py     # IFeatureModule
│       │   │   └── 📄 container.py          # IContainer
│       │   │
│       │   ├── 📁 use_cases/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 send_message.py       # SendMessageUseCase
│       │   │   ├── 📄 send_media.py         # SendMediaUseCase
│       │   │   ├── 📄 manage_session.py     # SessionManagementUseCase
│       │   │   └── 📄 get_conversation.py   # GetConversationHistoryUseCase
│       │   │
│       │   ├── 📁 services/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 event_bus.py          # InMemoryEventBus implementation
│       │   │   └── 📄 feature_registry.py   # FeatureRegistry
│       │   │
│       │   └── 📁 dtos/
│       │       ├── 📄 __init__.py
│       │       ├── 📄 outgoing_message.py   # OutgoingMessage DTO
│       │       └── 📄 incoming_message.py   # IncomingMessage DTO
│       │
│       ├── 📁 infrastructure/               # OUTER LAYER — implementations
│       │   ├── 📄 __init__.py
│       │   │
│       │   ├── 📁 neonize/                  # Neonize adapter
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 gateway.py            # NeonizeGateway: implements IMessagingGateway
│       │   │   ├── 📄 event_mapper.py       # Map Neonize events → Domain events
│       │   │   └── 📄 client_factory.py     # Create and configure Neonize client
│       │   │
│       │   ├── 📁 database/
│       │   │   ├── 📄 __init__.py
│       │   │   ├── 📄 base.py               # SQLAlchemy Base, engine factory
│       │   │   ├── 📄 models.py             # All SQLAlchemy ORM models
│       │   │   ├── 📁 repositories/
│       │   │   │   ├── 📄 session_repo.py   # SQLAlchemySessionRepository
│       │   │   │   ├── 📄 message_repo.py   # SQLAlchemyMessageRepository
│       │   │   │   ├── 📄 contact_repo.py   # SQLAlchemyContactRepository
│       │   │   │   └── 📄 conversation_repo.py
│       │   │   └── 📁 migrations/           # Alembic migrations
│       │   │       ├── 📄 env.py
│       │   │       ├── 📄 script.py.mako
│       │   │       └── 📁 versions/
│       │   │
│       │   ├── 📁 config/
│       │   │   ├── 📄 __init__.py
│       │   │   └── 📄 settings.py           # Pydantic Settings
│       │   │
│       │   ├── 📁 logging/
│       │   │   ├── 📄 __init__.py
│       │   │   └── 📄 setup.py              # structlog configuration
│       │   │
│       │   └── 📁 queue/                    # Optional: Task queue
│       │       ├── 📄 __init__.py
│       │       └── 📄 arq_worker.py         # ARQ worker configuration
│       │
│       └── 📁 features/                     # VERTICAL SLICES — feature modules
│           ├── 📄 __init__.py
│           │
│           ├── 📁 session/                  # Feature: Session Management
│           │   ├── 📄 __init__.py           # SessionFeature(IFeatureModule)
│           │   ├── 📄 manager.py            # SessionManager
│           │   ├── 📄 qr_handler.py         # QRDisplayHandler
│           │   └── 📄 reconnect.py          # ExponentialBackoffReconnector
│           │
│           ├── 📁 messaging/                # Feature: Messaging
│           │   ├── 📄 __init__.py           # MessagingFeature(IFeatureModule)
│           │   ├── 📄 sender.py             # MessageSender (high-level API)
│           │   ├── 📄 handlers.py           # InboundMessageHandlers
│           │   └── 📄 media.py              # MediaProcessor
│           │
│           ├── 📁 commands/                 # Feature: Command Routing
│           │   ├── 📄 __init__.py           # CommandsFeature(IFeatureModule)
│           │   ├── 📄 router.py             # CommandRouter
│           │   ├── 📄 registry.py           # CommandHandlerRegistry
│           │   ├── 📄 context.py            # CommandContext dataclass
│           │   ├── 📄 base.py               # BaseCommandHandler, ICommandHandler
│           │   └── 📁 handlers/             # Built-in command handlers
│           │       ├── 📄 __init__.py
│           │       ├── 📄 ping.py           # PingHandler: !ping → pong
│           │       └── 📄 help.py           # HelpHandler: !help
│           │
│           └── 📁 ai_integration/           # Feature: AI Integration (optional)
│               ├── 📄 __init__.py           # AIIntegrationFeature(IFeatureModule)
│               ├── 📄 context_builder.py    # ConversationContextBuilder
│               ├── 📁 providers/
│               │   ├── 📄 __init__.py
│               │   ├── 📄 base.py           # IAIProvider Protocol
│               │   ├── 📄 openai.py         # OpenAIProvider
│               │   ├── 📄 gemini.py         # GeminiProvider
│               │   └── 📄 noop.py           # NoopAIProvider (disabled state)
│               └── 📁 use_cases/
│                   └── 📄 ask_ai.py         # AskAIUseCase
│
├── 📁 tests/                                # Test suite
│   ├── 📄 __init__.py
│   ├── 📄 conftest.py                       # Shared fixtures
│   ├── 📁 unit/                             # Unit tests (no I/O)
│   │   ├── 📄 __init__.py
│   │   ├── 📁 domain/
│   │   │   ├── 📄 test_session_entity.py
│   │   │   ├── 📄 test_jid.py
│   │   │   ├── 📄 test_bot_command.py
│   │   │   └── 📄 test_command_parser.py
│   │   ├── 📁 application/
│   │   │   ├── 📄 test_send_message_use_case.py
│   │   │   ├── 📄 test_event_bus.py
│   │   │   └── 📄 test_command_router.py
│   │   └── 📁 features/
│   │       ├── 📄 test_ping_handler.py
│   │       └── 📄 test_help_handler.py
│   │
│   ├── 📁 integration/                      # Integration tests (with DB)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 conftest.py                   # DB fixtures (in-memory SQLite)
│   │   ├── 📄 test_session_repository.py
│   │   ├── 📄 test_message_repository.py
│   │   └── 📄 test_send_message_flow.py
│   │
│   ├── 📁 e2e/                              # End-to-end tests (manual/staged)
│   │   ├── 📄 README.md                     # Instruksi manual E2E tests
│   │   └── 📄 test_qr_pairing.py           # Hanya dijalankan manual
│   │
│   └── 📁 mocks/                            # Shared test doubles
│       ├── 📄 __init__.py
│       ├── 📄 mock_gateway.py               # MockMessagingGateway
│       ├── 📄 mock_event_bus.py             # MockEventBus
│       └── 📄 factories.py                  # factory-boy factories
│
├── 📁 docs/                                 # Documentation (semua 28 dokumen)
│   ├── 📄 01_product_vision.md
│   ├── 📄 02_domain_glossary.md
│   ├── ...
│   ├── 📁 adr/                              # Architectural Decision Records
│   └── 📁 features/                         # Per-feature specs
│
├── 📁 docker/                               # Docker configurations
│   ├── 📄 Dockerfile                        # Production image
│   ├── 📄 Dockerfile.dev                    # Development image
│   └── 📄 .dockerignore
│
├── 📁 scripts/                              # Utility scripts
│   ├── 📄 setup_dev.sh                      # Setup development environment
│   ├── 📄 run_tests.sh                      # Run all tests with coverage
│   └── 📄 migrate.sh                        # Run database migrations
│
├── 📁 .github/                              # GitHub configuration
│   ├── 📁 workflows/
│   │   ├── 📄 ci.yml                        # CI pipeline
│   │   └── 📄 cd.yml                        # CD pipeline
│   ├── 📁 ISSUE_TEMPLATE/
│   └── 📄 PULL_REQUEST_TEMPLATE.md
│
├── 📄 pyproject.toml                        # Project metadata + dependencies
├── 📄 uv.lock                               # Lockfile (committed to git)
├── 📄 alembic.ini                           # Alembic configuration
├── 📄 docker-compose.yml                    # Local development stack
├── 📄 docker-compose.prod.yml               # Production stack reference
├── 📄 .env.example                          # Template env vars (tidak ada nilai asli)
├── 📄 .gitignore
├── 📄 .pre-commit-config.yaml               # Pre-commit hooks
├── 📄 README.md                             # Project entry point
├── 📄 CONTRIBUTING.md
├── 📄 CHANGELOG.md
└── 📄 LICENSE
```

---

## 2. Aturan Struktur

### Dependency Rule (WAJIB)
```
domain/    → tidak boleh import dari layer mana pun
application/ → boleh import dari domain/ saja
infrastructure/ → boleh import dari domain/ dan application/
features/ → boleh import dari domain/, application/
           TIDAK BOLEH import dari infrastructure/ langsung
```

### Naming Rules
```
File: snake_case.py
Class: PascalCase
Interface: Prefix "I" → IMessageRepository, IEventBus
Use Case: Suffix "UseCase" → SendMessageUseCase
Feature Module: Suffix "Feature" → SessionFeature
Handler: Suffix "Handler" → PingHandler, QRDisplayHandler
Repository (impl): Prefix "SQLAlchemy" → SQLAlchemySessionRepository
```

### File Size Rules
```
Maksimum per file: 200 baris (guideline, bukan hard limit)
Jika lebih dari 300 baris: pertimbangkan split menjadi beberapa file
```

---

## 3. Import Guidelines

```python
# BENAR — absolute imports dari package root
from whatsapp_platform.domain.entities import WhatsAppSession
from whatsapp_platform.domain.value_objects import JID
from whatsapp_platform.application.interfaces import IMessagingGateway

# SALAH — relative imports (membuat refactoring sulit)
from ..domain.entities import WhatsAppSession
from ...value_objects import JID

# BENAR — stdlib imports pertama, lalu third-party, lalu internal
import asyncio
from datetime import datetime
from typing import Protocol

import structlog
from pydantic import BaseModel

from whatsapp_platform.domain.entities import WhatsAppSession
```

---

## References

- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-018: Coding Standards](./16_coding_standards.md)
- [DOC-019: DI Strategy](./17_di_strategy.md)
