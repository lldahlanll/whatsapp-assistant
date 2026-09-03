# 🏛️ Software Architecture Document (SAD)
# Neonize AI Platform — Production-Grade Enterprise Architecture

> **Document Status:** Approved Architecture Standard  
> **Role:** Senior Software Architect  
> **Target Version:** 1.0.0  
> **Last Updated:** 2026-08-03  

---

## 1. Executive Summary & Architectural Goals

**Neonize AI Platform** didesain menggunakan **Clean Architecture** (Robert C. Martin) yang dikombinasikan dengan **Domain-Driven Design (DDD)** dan **Event-Driven Architecture (EDA)**. 

Tujuan utama dari arsitektur ini adalah:
1. **Independent of Frameworks**: Logika bisnis murni terisolasi penuh dari FastAPI, Neonize, Redis, maupun PostgreSQL.
2. **Testability**: Seluruh aturan bisnis (*business rules*) dapat diuji secara terisolasi tanpa memerlukan jaringan, database, atau WhatsApp server.
3. **Independent of UI & Protocol**: Antarmuka web (FastAPI/Dashboard) maupun protokol perpesanan (Neonize) dapat diganti/diubah tanpa memengaruhi domain core.
4. **Scalability & Concurrency**: Arsitektur *async-first* (Python 3.13 `asyncio`) dengan *offloading* tugas berat ke antrean Redis.

---

## 2. Technology Stack Architecture

| Layer / Component | Technology | Version | Rationale |
|---|---|---|---|
| **Runtime Language** | Python | 3.13+ | Performa `asyncio` terbaru, `type` statement, immutability & type-safety. |
| **WhatsApp Protocol** | Neonize | Latest Stable | Binding Python performa tinggi berbasis Whatsmeow (Go backend). |
| **REST API & Gateway** | FastAPI | 0.110+ | Framework web async ultra-fast, otomatis OpenAPI spec, Pydantic v2 validation. |
| **Primary Database** | PostgreSQL | 16-alpine | Relational DB berstandar enterprise, dukungan JSONB & ACID transaksi. |
| **ORM & Migrations** | SQLAlchemy + Alembic | 2.0+ (Async) | `AsyncSession` native, Mypy strict support, migrasi skema terstruktur. |
| **Cache & Message Broker**| Redis | 7-alpine | In-memory cache cepat, pub/sub, dan task queue broker (ARQ). |
| **Containerization** | Docker & Compose | Multi-stage | Deployment terisolasi, non-root runner, persistent volumes. |

---

## 3. Clean Architecture Layer Breakdown

```
+-----------------------------------------------------------------------+
|                         PRESENTATION LAYER                            |
|             (FastAPI Controllers, Webhook Handlers, CLI)              |
|                                                                       |
|   +---------------------------------------------------------------+   |
|   |                     INFRASTRUCTURE LAYER                      |   |
|   |   (Neonize Adapter, SQLAlchemy Repos, Redis Cache, LLM Adapters)  |   |
|   |                                                               |   |
|   |   +-------------------------------------------------------+   |   |
|   |   |                  APPLICATION LAYER                    |   |   |
|   |   |     (Use Cases, DTOs, Event Bus, Port Interfaces)     |   |   |
|   |   |                                                       |   |   |
|   |   |   +-----------------------------------------------+   |   |   |
|   |   |   |                 DOMAIN LAYER                  |   |   |   |
|   |   |   |  (Entities, Value Objects, Domain Events,     |   |   |   |
|   |   |   |   Repository Contracts, Domain Services)      |   |   |   |
|   |   |   +-----------------------------------------------+   |   |   |
|   |   +-------------------------------------------------------+   |   |
|   +---------------------------------------------------------------+   |
+-----------------------------------------------------------------------+
```

### 3.1 Domain Layer (`src/domain/`)
- **Tanggung Jawab**: Menyimpan objek bisnis inti, aturan domain, dan invarian (*business invariants*).
- **Aturan Dependencies**: **TIDAK BOLEH** mengimpor library pihak ketiga, ORM, FastAPI, atau Neonize. Murni Python stdlib.
- **Komponen**: `Entities`, `Value Objects`, `Domain Events`, `Domain Services`, `Repository Contracts (Interfaces)`.

### 3.2 Application Layer (`src/application/`)
- **Tanggung Jawab**: Mengatur alur kerja aplikasi (*orchestration*) dan mengeksekusi use-case bisnis.
- **Aturan Dependencies**: Hanya mengimpor dari `Domain Layer`. Mengakses infrastruktur melalui *Interfaces (Ports)*.
- **Komponen**: `Use Cases`, `DTOs (Data Transfer Objects)`, `Event Bus Interfaces`, `Plugin Interfaces`.

### 3.3 Infrastructure Layer (`src/infrastructure/`)
- **Tanggung Jawab**: Implementasi teknis konkret dari interface yang didefinisikan di Application/Domain Layer.
- **Komponen**: `NeonizeGateway`, `SQLAlchemyRepositories`, `RedisCacheAdapter`, `OpenAI/Gemini Adapters`, `Alembic`.

### 3.4 Presentation Layer (`src/presentation/`)
- **Tanggung Jawab**: Titik masuk (*entry point*) interaksi eksternal (HTTP Requests, Dashboard, CLI).
- **Komponen**: `FastAPI Routers`, `Middlewares (Auth/RBAC)`, `Request/Response Schemas`.

---

## 4. Project Folder Structure

```text
neonize-ai-platform/
├── src/
│   └── platform_core/
│       ├── domain/                      # 1. DOMAIN LAYER (Pure Logic)
│       │   ├── entities/                # Session, Message, User, Conversation, Plugin
│       │   ├── value_objects/           # JID, MessageID, MessageStatus, BotCommand
│       │   ├── events/                  # MessageReceived, SessionConnected, AIResponded
│       │   ├── repositories/            # Interfaces: ISessionRepo, IMessageRepo, IUserRepo
│       │   └── exceptions/              # Custom Domain Exceptions
│       │
│       ├── application/                 # 2. APPLICATION LAYER (Use Cases)
│       │   ├── use_cases/               # ProcessIncomingMsg, AuthenticateUser, RouteAI
│       │   ├── dtos/                    # Request/Response DTOs
│       │   ├── ports/                   # Interfaces: IMessagingGateway, ICachePort, ILLMPort
│       │   └── services/                # EventBus, PluginRegistry, TaskScheduler
│       │
│       ├── infrastructure/              # 3. INFRASTRUCTURE LAYER (Adapters)
│       │   ├── whatsapp/                # Neonize Client Adapter, Event Mapper
│       │   ├── database/                # SQLAlchemy Models, Alembic, Repository Impl
│       │   ├── cache/                   # Redis Session Storage & Memory Adapter
│       │   ├── ai/                      # OpenAI, Gemini, Vision, OCR, RAG Adapters
│       │   ├── queue/                   # ARQ Worker & Redis Producer Setup
│       │   └── logging/                 # Structlog JSON Logger Configuration
│       │
│       ├── presentation/                # 4. PRESENTATION LAYER (API & UI)
│       │   ├── api/                     # FastAPI Routers (v1/auth, v1/sessions, v1/ai)
│       │   ├── middlewares/             # JWT Auth, RBAC Permission Enforcer, CORS
│       │   └── schemas/                 # Pydantic API Request/Response Schemas
│       │
│       ├── plugins/                     # 5. PLUGIN SYSTEM (Modular Extensions)
│       │   ├── base.py                  # Plugin Interface Contract
│       │   └── official/                # Built-in Plugins (Weather, OCR, Calculator)
│       │
│       ├── container.py                 # Dependency Injection (DI) Wire
│       ├── app.py                       # FastAPI Application Bootstrap
│       └── __main__.py                  # CLI & Application Entry Point
│
├── tests/                               # Unit, Integration, & E2E Tests
├── docker/                              # Dockerfile & Docker Compose Configs
├── pyproject.toml                       # Dependency & Tool Configuration
└── alembic.ini                          # Database Migration Config
```

---

## 5. Dependency Rules & Dependency Injection (DI)

Arsitektur ini menegaskan **Dependency Inversion Principle**:
- Layer yang lebih tinggi mengabstraksi layer yang lebih rendah melalui *Interfaces (Ports)*.
- `container.py` menginstansiasi *Adapters* (misal: `SQLAlchemySessionRepository`) dan meng-inject-nya ke dalam *Use Cases* yang membutuhkan `ISessionRepository`.

```text
[ Presentation (FastAPI) ] ---> [ Application (Use Case) ] ---> [ Domain (Entities) ]
                                          |
                                          v (Depends on Interface)
                                  [ Port Interface ]
                                          ^
                                          | (Implements Interface)
                               [ Infrastructure Adapter ]
```

---

## 6. Detailed Data & Execution Flows (With ASCII Diagrams)

---

### 6.1 Flow WhatsApp Connection & Pairing (QR / Pairing Code)

Proses inisialisasi koneksi Neonize, pendaftaran sesi baru via QR Code atau 8-digit Pairing Code, serta penanganan Reconnect.

```text
[User / Admin]       [FastAPI / CLI]       [Session UseCase]       [Neonize Gateway]      [WhatsApp Server]
      |                     |                      |                       |                      |
      |-- 1. Request Pair ->|                      |                       |                      |
      |   (QR / Code)       |-- 2. Init Session -->|                       |                      |
      |                     |                      |-- 3. Connect Client ->|                      |
      |                     |                      |                       |-- 4. Handshake ----->|
      |                     |                      |                       |<-- 5. Return Event --|
      |                     |                      |                       |   (QR/Pairing Code)  |
      |<-- 6. Render QR/Code|<---------------------|<-- Publish Event -----|                      |
      |                       (Display Code / Web UI)                      |                      |
      |                                                                    |                      |
      |-- 7. Scan QR / Input Code on WhatsApp Phone App ----------------------------------------->|
      |                                                                    |                      |
      |                                                                    |<-- 8. Pair Success --|
      |                                                                    |    (PairSuccessEv)   |
      |                     |                      |<-- 9. Emit Event -----|                      |
      |                     |                      |   (SessionConnected)  |                      |
      |                     |                      |-- 10. Persist State ->|                      |
      |                     |                      |    (DB & Redis)       |                      |
```

---

### 6.2 Flow Inbound Message Processing

Alur penanganan pesan masuk dari WhatsApp melalui Neonize, dipisahkan secara asinkron menggunakan Redis Queue.

```text
[WhatsApp Server] ---> (WebSocket) ---> [Neonize Gateway]
                                             |
                                   1. Map to Domain Event
                                             v
                                   [InMemory Event Bus]
                                             |
                                   2. Enqueue Task (Async)
                                             v
                                    [Redis Task Queue]
                                             |
                                   3. Worker Dequeue Task
                                             v
                                  [ProcessMessage UseCase]
                                             |
                   +-------------------------+-------------------------+
                   |                                                   |
           (If Bot Command)                                    (If AI Message)
                   |                                                   |
                   v                                                   v
         [Command Router]                                        [AI Router Service]
                   |                                                   |
                   +-------------------------+-------------------------+
                                             |
                                   4. Generate Outbound DTO
                                             v
                                  [SendMessage UseCase]
```

---

### 6.3 Flow Outbound Message Execution

Alur pengiriman pesan balasan kembali ke pengguna WhatsApp.

```text
[Use Case / Plugin] ---> [SendMessage UseCase] ---> [IMessagingGateway Port]
                                                               |
                                                     (Implemented By)
                                                               v
                                                      [Neonize Gateway]
                                                               |
                                                    (Format to Protobuf)
                                                               v
                                                    [Whatsmeow Go Core]
                                                               |
                                                       (WebSocket E2EE)
                                                               v
                                                      [WhatsApp Server]
```

---

### 6.4 Flow AI Processing (Router, Memory, RAG, Vision & Tool Calling)

Alur penanganan pesan kecerdasan buatan terintegrasi (*AI Pipeline*).

```text
[Incoming Message] ---> [AI Router Service]
                              |
              +---------------+---------------+
              |                               |
    1. Fetch Context Memory           2. Detect Content Type
              v                               v
    [Redis Conversation Memory]      [Text / Vision / Audio OCR]
              |                               |
              +---------------+---------------+
                              |
                     3. Query Knowledge?
                              |
                +-------------+-------------+
                | YES                       | NO
                v                           v
     [Vector DB (Qdrant/RAG)]      [Direct LLM Prompt]
                |                           |
                +-------------+-------------+
                              |
                     4. Execute LLM Call
                              v
                  [OpenAI / Gemini LLM Engine]
                              |
                    5. Returns Function Call?
                              |
                +-------------+-------------+
                | YES                       | NO
                v                           v
     [Plugin / Tool Executor]       [Final AI Text Response]
                |                           |
                +---- (Re-prompt LLM) ----->+
                                            |
                                            v
                                [Send Outbound Response]
```

---

### 6.5 Flow Request API / Dashboard (Authentication & RBAC)

Alur HTTP request dari Admin Web Dashboard menuju FastAPI dengan verifikasi JWT dan RBAC.

```text
[Admin Dashboard] ---> (HTTP Request + Bearer JWT) ---> [FastAPI Router]
                                                              |
                                                    1. Auth Middleware
                                                              v
                                                    [JWT Verification]
                                                              |
                                                    2. Check Permissions
                                                              v
                                                    [RBAC Guard Enforcer]
                                                              |
                                                    3. Execute Use Case
                                                              v
                                                   [Management UseCase]
                                                              |
                                                    4. Query Read/Write
                                                              v
                                                    [PostgreSQL / Redis]
```

---

### 6.6 Flow Database (SQLAlchemy 2.x Async & Alembic)

Arsitektur akses data relasional menggunakan SQLAlchemy 2.x `AsyncSession` dan pola *Unit of Work*.

```text
[Application Use Case]
         |
  1. Acquire Session
         v
[AsyncSessionFactory] ---> Creates ---> [SQLAlchemy AsyncSession]
                                                 |
                                         2. Repositories Work
                                                 v
                                   [SQLAlchemy Repository Impl]
                                                 |
                                         3. Async Execution
                                                 v
                                        [asyncpg Driver]
                                                 |
                                         4. SQL Query/Transaction
                                                 v
                                       [PostgreSQL Database]

* Migration Management: Alembic Script ---> (DDL Changes) ---> [PostgreSQL Database]
```

---

### 6.7 Flow Cache & Conversation Memory (Redis)

Pengelolaan *sliding-window conversational memory* dan cache status di Redis.

```text
[AI Processing Node]
         |
         +--- 1. Read Recent Context (LRU Cache) -----> [Redis Cache Engine]
         |                                                      |
         |                                            (Returns JSON Context)
         |                                                      |
         +--- 2. Append User/Assistant Message ---------------->+
         |                                                      |
         +--- 3. Check Context Exceeded Limit?                  |
                     |                                          |
                     +-- (YES) -> Summarize & Truncate Key ---->+
```

---

### 6.8 Flow Plugin System Lifecycle

Alur pendaftaran, penemuan (*discovery*), dan eksekusi plugin dinamis.

```text
[System Bootstrap] ---> 1. Scan /src/plugins/ ---> [Plugin Registry]
                                                         |
                                               2. Register Interfaces
                                                         |
[Incoming Event] ----------------------------------------+
       |
3. Match Trigger Criteria (Command / Hook Point)
       |
       v
[Execute Plugin.run()] ---> 4. Return Output Payload ---> [Event Pipeline]
```

---

### 6.9 Flow WhatsApp Protocol & Media Handling

Handling pesan media (Gambar, Audio Voice Note ke Text, Dokumen PDF).

```text
[WhatsApp Server] ---> [Neonize MessageEv]
                              |
                    1. Contains Media Payload?
                              v
                  [Media Downloader Adapter]
                              |
                    2. Convert / Parse Media
                              v
       +----------------------+----------------------+
       |                      |                      |
[Audio (Voice Note)]    [Image File]           [PDF Document]
       |                      |                      |
 (Whisper STT)          (Vision / OCR)       (PyMuPDF Reader)
       |                      |                      |
       +----------------------+----------------------+
                              |
                    3. Normalized Text Result
                              v
                     [Inject to AI Router]
```

---

## 7. Security & Isolation Architecture

1. **Isolation of Credential Data**: SQLite / PostgreSQL credentials Neonize dipisahkan dari database utama bisnis.
2. **Network Isolation**: PostgreSQL dan Redis tidak dipublikasikan ke port publik; hanya dapat diakses di dalam internal Docker Network bridge.
3. **Application Least Privilege**: Kontainer Docker berjalan menggunakan user `appuser` (non-root UID 1000).

---

## 8. Deployment Topology (Docker Compose Stack)

```text
+-----------------------------------------------------------------------------------+
|                                 DOCKER HOST                                       |
|                                                                                   |
|  +-----------------------+     +-----------------------+     +-----------------+  |
|  |   app (FastAPI/Core)  |     |   worker (ARQ Engine) |     |  Prometheus     |  |
|  |   Port: 8000:8000     |     |   (Background Async)  |     |  Port: 9090     |  |
|  +-----------+-----------+     +-----------+-----------+     +--------+--------+  |
|              |                             |                          |           |
|              +-----------------------------+--------------------------+           |
|                                            |                                      |
|                                  (Docker Internal Bridge)                         |
|                                            |                                      |
|              +-----------------------------+--------------------------+           |
|              |                             |                          |           |
|  +-----------+-----------+     +-----------+-----------+     +--------+--------+  |
|  |  postgres (DB Rel)    |     |    redis (Cache/Queue) |     |  Grafana        |  |
|  |  Port: 5432 (Internal)|     |    Port: 6379 (Internal|     |  Port: 3000     |  |
|  +-----------------------+     +-----------------------+     +-----------------+  |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## References

- [DOC-004: PRD Neonize AI Platform](./04_prd_neonize_ai_platform.md)
- [DOC-006: Technology Stack](./06_tech_stack.md)
- [DOC-008: Domain Model](./08_domain_model.md)
- [DOC-010: Data Architecture](./10_data_architecture.md)
