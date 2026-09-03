# DOC-009 · System Context Diagram & C4 Model

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Architect  

---

## C4 Model Overview

C4 Model (Simon Brown) mendokumentasikan arsitektur dalam 4 level zoom:
- **Level 1 (Context)**: Sistem kita dan hubungannya dengan dunia luar
- **Level 2 (Container)**: Aplikasi dan services yang berjalan
- **Level 3 (Component)**: Komponen dalam satu container
- **Level 4 (Code)**: Class diagram (di-generate otomatis dari kode)

---

## Level 1: System Context Diagram

```mermaid
C4Context
    title System Context — WhatsApp Platform

    Person(developer, "Developer", "Mengkonfigurasi dan mengembangkan platform")
    Person(endUser, "End User", "Mengirim pesan via WhatsApp")

    System(platform, "WhatsApp Platform", "Platform otomasi WhatsApp berbasis Python + Neonize")

    System_Ext(whatsapp, "WhatsApp Server", "Server WhatsApp (Meta) — mengirim/menerima pesan E2EE")
    System_Ext(llmApi, "LLM API", "OpenAI / Gemini / Local model untuk AI response")
    System_Ext(webhookTarget, "External Webhook", "Sistem eksternal yang menerima notifikasi event")

    Rel(endUser, whatsapp, "Mengirim pesan", "WhatsApp App")
    Rel(whatsapp, platform, "Meneruskan pesan & events", "Whatsmeow protocol (via Neonize)")
    Rel(platform, whatsapp, "Mengirim pesan", "Whatsmeow protocol (via Neonize)")
    Rel(platform, llmApi, "Request AI completion", "HTTPS / REST")
    Rel(platform, webhookTarget, "Kirim event notification", "HTTPS / POST")
    Rel(developer, platform, "Konfigurasi & deploy", "Docker / SSH / CLI")
```

---

## Level 2: Container Diagram

```mermaid
C4Container
    title Container Diagram — WhatsApp Platform

    Person(developer, "Developer")
    Person(endUser, "End User")

    System_Ext(whatsapp, "WhatsApp Server")
    System_Ext(llmApi, "LLM API")

    Container_Boundary(platform, "WhatsApp Platform") {
        Container(app, "Platform Application", "Python 3.13 / asyncio", "Proses utama: session management, event handling, command routing, feature modules")
        ContainerDb(db, "Application Database", "SQLite (dev) / PostgreSQL (prod)", "Simpan session metadata, message history, contact data")
        ContainerDb(sessionDb, "Neonize Session Storage", "SQLite (default)", "Simpan Neonize session credentials untuk reconnect")
        Container(queue, "Task Queue", "ARQ + Redis (optional)", "Async task processing untuk heavy operations")
        Container(redis, "Redis", "Redis 7", "Task queue broker, caching (optional)")
    }

    Rel(endUser, whatsapp, "Chat")
    Rel(whatsapp, app, "Events via callback", "Neonize/Whatsmeow")
    Rel(app, whatsapp, "Send messages", "Neonize/Whatsmeow")
    Rel(app, db, "Read/Write data", "SQLAlchemy async")
    Rel(app, sessionDb, "Read/Write session", "Neonize built-in")
    Rel(app, queue, "Enqueue tasks", "ARQ client")
    Rel(queue, redis, "Store tasks", "Redis protocol")
    Rel(app, llmApi, "AI requests", "HTTPS")
    Rel(developer, app, "Deploy & configure")
```

---

## Level 3: Component Diagram — Platform Application

```mermaid
C4Component
    title Component Diagram — Platform Application

    Container_Boundary(app, "Platform Application") {
        
        Component(bootstrap, "App Bootstrap", "app.py", "Inisialisasi semua komponen, DI wiring, lifecycle management")
        Component(container, "DI Container", "container.py", "Dependency injection — instantiate dan wire semua dependencies")

        Component_Boundary(infra, "Infrastructure Layer") {
            Component(gateway, "NeonizeGateway", "infrastructure/neonize/", "Adapter untuk Neonize library. Implements IMessagingGateway. Map Neonize events ke domain events.")
            Component(sessionRepo, "SQLAlchemySessionRepository", "infrastructure/database/", "Implements ISessionRepository. Persistence via SQLAlchemy 2.x async.")
            Component(messageRepo, "SQLAlchemyMessageRepository", "infrastructure/database/", "Implements IMessageRepository.")
            Component(config, "Settings", "infrastructure/config/", "Pydantic Settings — load & validate env vars")
            Component(logger, "StructuredLogger", "infrastructure/logging/", "structlog setup — JSON output production, pretty dev")
        }

        Component_Boundary(appLayer, "Application Layer") {
            Component(eventBus, "InMemoryEventBus", "application/", "Internal pub/sub. Dispatch domain events ke registered handlers.")
            Component(sendUC, "SendMessageUseCase", "application/use_cases/", "Orchestrate: validate -> call gateway -> save -> emit event")
            Component(sessionUC, "SessionManagementUseCase", "application/use_cases/", "Manage session lifecycle")
        }

        Component_Boundary(features, "Features Layer") {
            Component(sessionFeat, "SessionFeature", "features/session/", "Handle QR display, reconnect logic, session status reporting")
            Component(cmdRouter, "CommandRouter", "features/commands/", "Parse incoming messages, route ke CommandHandler yang sesuai")
            Component(msgFeat, "MessagingFeature", "features/messaging/", "Register handlers untuk inbound message events")
            Component(aiFeat, "AIIntegrationFeature", "features/ai_integration/", "LLM provider interface + default message handler")
        }
    }

    Rel(bootstrap, container, "Configure")
    Rel(container, gateway, "Inject")
    Rel(container, eventBus, "Inject")
    Rel(gateway, eventBus, "Publish events")
    Rel(eventBus, cmdRouter, "Dispatch MessageReceived")
    Rel(eventBus, msgFeat, "Dispatch MessageReceived")
    Rel(eventBus, sessionFeat, "Dispatch Session events")
    Rel(cmdRouter, sendUC, "Trigger send response")
    Rel(aiFeat, sendUC, "Trigger AI response")
    Rel(sendUC, gateway, "Call send")
    Rel(sendUC, messageRepo, "Save message")
    Rel(sessionUC, sessionRepo, "Save session state")
```

---

## Level 3: Component Diagram — Feature Module (Detail)

Setiap feature module memiliki struktur internal yang konsisten:

```mermaid
graph TD
    subgraph "Feature: commands"
        A["__init__.py\n(IFeatureModule impl)"] --> B["handler.py\n(Base CommandHandler)"]
        A --> C["router.py\n(CommandRouter)"]
        A --> D["parser.py\n(CommandParserService)"]
        A --> E["handlers/\n(konkret handlers)"]
        E --> E1["help_handler.py"]
        E --> E2["ping_handler.py"]
        E --> E3["..."]
    end
```

---

## Deployment Diagram

```mermaid
graph TD
    subgraph "Developer Machine (Dev)"
        compose["docker-compose.yml"]
        appDev["whatsapp-platform container"]
        sqliteDev["SQLite file volume"]
        compose --> appDev
        appDev --> sqliteDev
    end

    subgraph "Production Server (VPS/Cloud)"
        nginx["Nginx (optional reverse proxy)"]
        appProd["whatsapp-platform container"]
        postgres["PostgreSQL container"]
        redis["Redis container (optional)"]
        volume["Persistent Volume (session files)"]
        
        nginx --> appProd
        appProd --> postgres
        appProd --> redis
        appProd --> volume
    end

    Internet["WhatsApp Server (Meta)"]
    appDev <--> Internet
    appProd <--> Internet
```

---

## Sequence Diagram: Inbound Message Flow

```mermaid
sequenceDiagram
    participant WA as WhatsApp Server
    participant NEO as Neonize (Go)
    participant GW as NeonizeGateway
    participant EB as EventBus
    participant CR as CommandRouter
    participant CH as CommandHandler
    participant UC as SendMessageUseCase
    participant DB as Database

    WA->>NEO: MessageEv (protobuf)
    NEO->>GW: Python callback (MessageEv)
    GW->>GW: Map MessageEv -> IncomingMessage
    GW->>GW: Create MessageReceived domain event
    GW->>EB: publish(MessageReceived)
    EB->>CR: dispatch(MessageReceived)
    CR->>CR: parse BotCommand from body
    alt Command found
        CR->>CH: handle(CommandContext)
        CH->>UC: execute(OutgoingMessage)
        UC->>GW: send_text(to_jid, body)
        UC->>DB: save(Message)
        GW->>NEO: SendMessage()
        NEO->>WA: Send message
    else No command
        CR->>EB: publish(UnknownCommandReceived)
    end
```

---

## Sequence Diagram: Session Startup Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant APP as App Bootstrap
    participant CTR as DI Container
    participant GW as NeonizeGateway
    participant EB as EventBus
    participant SF as SessionFeature
    participant WA as WhatsApp Server

    Dev->>APP: python -m whatsapp_platform
    APP->>CTR: build_container()
    CTR->>GW: instantiate NeonizeGateway
    CTR->>EB: instantiate EventBus
    APP->>GW: start()
    GW->>GW: Check existing session in DB
    alt No session / session expired
        GW->>EB: publish(QRCodeGenerated)
        EB->>SF: dispatch(QRCodeGenerated)
        SF->>Dev: Display QR in terminal
        Dev->>WA: Scan QR with phone
        WA->>GW: Auth confirmation (PairSuccessEv)
        GW->>GW: Save session credentials
    end
    GW->>WA: Connect (WebSocket)
    WA->>GW: ConnectedEv
    GW->>EB: publish(SessionConnected)
    EB->>SF: dispatch(SessionConnected)
    SF->>Dev: Log "Connected successfully"
```

---

## References

- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-008: Domain Model](./08_domain_model.md)
- [DOC-023: Deployment Plan](./21_deployment_plan.md)
