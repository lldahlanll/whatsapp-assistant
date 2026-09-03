# DOC-005 · Architecture Overview Document (AOD)

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Software Architect  

---

## 1. Pola Arsitektur Yang Dipilih

Platform ini menggunakan **Clean Architecture** (Robert C. Martin) yang dikombinasikan dengan **Feature-Based Vertical Slice** untuk pengorganisasian kode.

### Mengapa Clean Architecture?

1. **Testability**: Domain logic bisa di-test tanpa Neonize, database, atau network.
2. **Independence**: Setiap layer bisa diganti tanpa memengaruhi layer lain.
3. **Explicitness**: Dependency hanya mengalir ke dalam (ke domain), tidak pernah ke luar.

### Mengapa Feature-Based (bukan pure layered)?

Layer-based structure (`controllers/`, `services/`, `repositories/`) membuat fitur tersebar di seluruh codebase. Feature-based memastikan semua yang berkaitan dengan satu fitur berada dalam satu folder.

---

## 2. Layer Diagram

```
+----------------------------------------------------------+
|                   INFRASTRUCTURE LAYER                    |
|  (Neonize Gateway, SQLAlchemy Repos, ARQ Queue, Config)  |
|                                                          |
|   +--------------------------------------------------+   |
|   |              APPLICATION LAYER                   |   |
|   |   (Use Cases, Application Services, DTOs)        |   |
|   |                                                  |   |
|   |   +------------------------------------------+  |   |
|   |   |           DOMAIN LAYER                   |  |   |
|   |   |  (Entities, Value Objects, Domain Events, |  |   |
|   |   |   Repository Interfaces, Domain Services) |  |   |
|   |   +------------------------------------------+  |   |
|   +--------------------------------------------------+   |
+----------------------------------------------------------+

       DEPENDENCY RULE: Arrows point INWARD only.
       Infrastructure -> Application -> Domain
       Domain knows NOTHING about outer layers.
```

---

## 3. Dependency Rule (Aturan Tidak Boleh Dilanggar)

```
ATURAN ABSOLUT:
  domain/    --> tidak boleh import dari: application/, infrastructure/, features/
  application/ --> tidak boleh import dari: infrastructure/
  infrastructure/ --> BOLEH import dari: domain/, application/
  features/ --> boleh import dari: domain/, application/
               TIDAK BOLEH import langsung dari: infrastructure/neonize/
```

---

## 4. Komponen Utama

### 4.1 Domain Layer (`src/domain/`)

**Tanggung jawab:** Business logic murni. Tidak boleh ada import dari library eksternal (kecuali stdlib).

| Komponen | Deskripsi |
|----------|-----------|
| `entities/` | Objek dengan identitas unik (Session, Message, Contact, Conversation) |
| `value_objects/` | Objek immutable tanpa identitas (JID, MessageID, BotCommand, MessageStatus) |
| `events/` | Domain events (MessageReceived, SessionConnected, CommandExecuted) |
| `repositories/` | Abstract interfaces untuk persistence (ISessionRepository, IMessageRepository) |
| `services/` | Domain services — logika yang tidak cocok di satu entity |
| `exceptions/` | Custom domain exceptions |

### 4.2 Application Layer (`src/application/`)

**Tanggung jawab:** Mengkoordinasikan domain objects untuk menyelesaikan use case. Mengatur aliran data.

| Komponen | Deskripsi |
|----------|-----------|
| `use_cases/` | Satu kelas per use case (SendMessageUseCase, ParseCommandUseCase) |
| `services/` | Application services yang digunakan oleh banyak use case |
| `dtos/` | Data Transfer Objects untuk komunikasi antar layer |
| `interfaces/` | Interfaces yang harus diimplementasikan infrastructure (IMessagingGateway, IEventBus) |
| `event_bus.py` | Interface dan implementasi in-memory event bus |

### 4.3 Infrastructure Layer (`src/infrastructure/`)

**Tanggung jawab:** Implementasi konkret. Framework, library, database, network.

| Komponen | Deskripsi |
|----------|-----------|
| `neonize/` | Adapter/Gateway untuk Neonize library |
| `database/` | SQLAlchemy models, repository implementations, Alembic migrations |
| `queue/` | Task queue implementation (ARQ atau Celery) |
| `config/` | Pydantic Settings, environment loading |
| `logging/` | Structured logging setup (structlog) |

### 4.4 Features Layer (`src/features/`)

**Tanggung jawab:** Vertical slices per fitur. Setiap feature adalah unit yang dapat berdiri sendiri.

| Feature | Deskripsi |
|---------|-----------|
| `session/` | Session management, QR handling, reconnect logic |
| `messaging/` | Send/receive text dan media |
| `commands/` | Command parser, router, base handler |
| `ai_integration/` | LLM provider interface + implementations |
| `scheduler/` | Scheduled message dan broadcast |
| `webhooks/` | Outbound webhook untuk integrasi eksternal |

### 4.5 Entry Point (`src/`)

| File | Deskripsi |
|------|-----------|
| `__main__.py` | Entry point: `python -m whatsapp_platform` |
| `container.py` | Dependency Injection Container — tempat semua dependensi di-wire |
| `app.py` | Application bootstrap dan lifecycle management |

---

## 5. Aliran Data (Data Flow)

### 5.1 Pesan Masuk (Inbound)

```
WhatsApp Server
      |
      v
[Neonize Go Backend]  <-- manages protocol, encryption
      |
      v (MessageEv callback)
[NeonizeGateway]  -- maps MessageEv -> IncomingMessage
      |
      v (publish)
[InternalEventBus]
      |
      +------------> [AuditLogger]
      |
      +------------> [CommandRouter]
      |                    |
      |                    v
      |              [CommandHandler.handle(ctx)]
      |                    |
      |                    v
      |              [SendMessageUseCase]
      |
      +------------> [AIIntegrationHandler] (jika enabled)
```

### 5.2 Pesan Keluar (Outbound)

```
[Any Handler / Use Case]
      |
      v (OutgoingMessage DTO)
[SendMessageUseCase]
      |
      v (calls interface)
[IMessagingGateway.send_text() / send_media()]
      |
      v (implementation)
[NeonizeGateway]
      |
      v
[Neonize API Call]
      |
      v
[WhatsApp Server]
```

---

## 6. Dependency Injection Architecture

Platform menggunakan **manual DI** dengan `container.py` sebagai pusat konfigurasi.

```python
# Contoh konseptual container.py

class Container:
    # Infrastructure
    db: Database = singleton(SQLiteDatabase)
    event_bus: IEventBus = singleton(InMemoryEventBus)
    gateway: IMessagingGateway = singleton(NeonizeGateway)
    
    # Repositories
    session_repo: ISessionRepository = singleton(SQLAlchemySessionRepository, db=db)
    message_repo: IMessageRepository = singleton(SQLAlchemyMessageRepository, db=db)
    
    # Use Cases
    send_message_use_case: SendMessageUseCase = transient(
        SendMessageUseCase, gateway=gateway, message_repo=message_repo
    )
    
    # Features
    command_router: CommandRouter = singleton(
        CommandRouter, event_bus=event_bus
    )
```

---

## 7. Event-Driven Architecture

Platform menggunakan **internal event bus** (in-process pub/sub) untuk decoupling antar komponen.

**Prinsip:**
- Event producers tidak tahu siapa yang mengkonsumsi event mereka
- Event consumers mendaftar ke event bus secara eksplisit
- Domain events adalah immutable value objects

**Event Flow:**
```
Producer (NeonizeGateway)
    --> publish(MessageReceived event)
        --> EventBus.dispatch(event)
            --> Handler1.handle(event)
            --> Handler2.handle(event)
            --> Handler3.handle(event)
```

Semua handlers berjalan secara **async** dan **concurrent** (via `asyncio.gather`).

---

## 8. Async Programming Model

```
Main asyncio event loop
├── Neonize connection listener (always running)
├── Reconnect manager (monitoring)
├── Health check task (periodic)
└── Task queue worker (if enabled)

Semua I/O operations: async/await
CPU-intensive tasks: delegasikan ke asyncio.to_thread()
```

---

## 9. Prinsip Desain Yang Tidak Boleh Dilanggar

1. **Domain layer adalah pure Python** — tidak ada Neonize, SQLAlchemy, atau framework di sini.
2. **Neonize tidak pernah diakses langsung dari use case** — selalu via `IMessagingGateway`.
3. **Tidak ada business logic di Infrastructure** — hanya translation dan technical concerns.
4. **Semua dependensi di-inject, tidak di-instantiate langsung di dalam class**.
5. **Setiap use case memiliki satu tanggung jawab** (Single Responsibility Principle).
6. **Event handlers harus idempotent** — aman bila dipanggil lebih dari sekali.
7. **Tidak ada `print()` statement di kode production** — gunakan `structlog`.

---

## 10. Trade-offs Yang Diterima

| Trade-off | Keputusan | Alasan |
|-----------|-----------|--------|
| Kompleksitas lebih tinggi dari "simple script" | Diterima | Long-term maintainability lebih penting |
| Lebih banyak file dan folder | Diterima | Navigasi lebih mudah, bukan lebih banyak kode |
| Manual DI vs DI framework | Manual DI (awal) | Lebih mudah dipahami, bisa switch ke framework later |
| In-memory event bus vs message broker | In-memory (MVP) | Cukup untuk single-instance; bisa diganti untuk scaling |
| SQLite vs PostgreSQL | SQLite (dev), Postgres (prod) | Developer experience tanpa overhead setup DB |

---

## References

- [DOC-006: Tech Stack](./06_tech_stack.md)
- [DOC-007: ADRs](./adr/)
- [DOC-008: Domain Model](./07_domain_model.md)
- [DOC-009: C4 Diagrams](./08_c4_diagrams.md)
- [DOC-017: Project Structure](./15_project_structure.md)
- [DOC-019: DI Strategy](./17_di_strategy.md)
