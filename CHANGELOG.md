# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-07

### Added
- **Core Clean Architecture & DDD Framework**:
  - Domain Entities: `Session`, `Message`, `Conversation`, `Contact`.
  - Value Objects: `JID`, `SessionStatus`, `MessageStatus`, `MessageContent` (`TextContent`, `MediaContent`), `BotCommand`.
  - Domain Events: `SessionConnected`, `SessionDisconnected`, `SessionQRCodeReceived`, `SessionPairStatusReceived`, `MessageReceived`, `MessageSent`, `MessageDelivered`, `MessageRead`, `CommandReceived`, `CommandExecuted`, `CommandFailed`.
  - Interfaces & Exception Hierarchy (`DomainException`, `GatewayException`, etc.).
- **Application & Event Bus**:
  - `IEventBus` and `EventBus` (in-memory async event bus with exception isolation).
  - `FeatureRegistry` lifecycle orchestrator (`IFeatureModule`).
  - Use Cases: `SendMessageUseCase`, `ReceiveMessageUseCase`.
- **Infrastructure & Database Persistence**:
  - SQLAlchemy 2.0 Async ORM models (`SessionModel`, `MessageModel`, `ConversationModel`, `ContactModel`) and Alembic DB migrations for SQLite storage.
  - Repositories: `SessionRepository`, `MessageRepository`, `ConversationRepository`, `ContactRepository`.
  - Config management with `pydantic-settings` v2 (`Settings`) supporting `.env`.
  - Structured logging with `structlog`.
  - `NeonizeGateway` adapter bridging background thread event loop of `neonize` engine to domain events and asyncio bus.
- **Vertical Slice Features**:
  - `SessionFeature`: WhatsApp connection lifecycle, QR pairing, and event bus injection.
  - `MessagingFeature`: Auto-persistence of incoming/outgoing messages and `Conversation` aggregate updates.
  - `CommandsFeature`: `CommandRouter` and built-in command handlers (`!ping`, `!help`, `!echo`, `!info`, `!group`).
  - `MediaProcessor`: PDF text extraction, Image OCR, Audio transcription fallback pipeline.
- **Test Suite**:
  - Full test suite with 102 passing unit and integration tests (`pytest`, `pytest-asyncio`).
  - Mocks for `IMessagingGateway` and `IEventBus`.
- **Application Lifecycle**:
  - `Application` runner in `app.py` with DI container wiring (`Container`) and graceful signal handling (SIGINT/SIGTERM).

## [0.0.1] - 2026-08-03

### Added
- Complete pre-coding technical documentation suite (28 documents).
- Clean Architecture, DDD, and Feature-Based project structural plan.
- Specifications for Neonize gateway integration, event catalog, and session lifecycle.
