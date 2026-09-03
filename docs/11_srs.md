# DOC-011 · Software Requirements Specification (SRS)

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** System Analyst + QA Engineer  

---

## 1. Introduction

### 1.1 Purpose
Dokumen ini menterjemahkan PRD (DOC-004) ke dalam spesifikasi teknis yang presisi untuk developer dan QA. Setiap requirement memiliki ID yang bisa di-trace ke PRD dan ke test cases.

### 1.2 Scope
Mencakup seluruh MVP (v0.1.0 hingga v0.9.0) dari WhatsApp Platform.

### 1.3 Definitions
Semua term mengikuti [DOC-002: Domain Glossary](./02_domain_glossary.md).

---

## 2. System Overview

Platform ini adalah **single-process, async Python application** yang:
- Menjaga satu koneksi WebSocket ke WhatsApp server via Neonize
- Mempublikasikan domain events ke internal event bus
- Memproses events via feature module handlers
- Menyimpan state ke database (SQLite/PostgreSQL)

---

## 3. Functional Requirements — Spesifikasi Detail

---

### 3.1 Session Management

#### SRS-FR-001: QR Code Authentication

```
Requirement:    FR-001 (dari PRD)
Priority:       Must Have
Precondition:   Tidak ada session valid tersimpan di database
Trigger:        Aplikasi dijalankan

Input:          - Tidak ada (triggered by startup)
Output:         - QR code ditampilkan di stdout sebagai ASCII art atau string
                - Log entry: level=INFO, event="qr_generated", session_id="..."

Processing:
  1. Startup → cek session di database
  2. Tidak ada session → Neonize generate QR
  3. QRCodeGenerated domain event dipublish
  4. SessionFeature handler display QR ke terminal
  5. Wait for scan (max 60 detik)
  6. QR di-scan → PairSuccessEv diterima dari Neonize
  7. Session disimpan ke database
  8. SessionConnected event dipublish

Error Handling:
  - QR timeout (60s): Generate QR baru, ulangi proses
  - Max QR attempts (3x): Log ERROR, exit dengan code 1
  
Performance:
  - QR harus muncul dalam < 5 detik dari startup
```

---

#### SRS-FR-002: Session Persistence

```
Requirement:    FR-002 (dari PRD)
Priority:       Must Have

Input:          - Neonize session credentials (internal format)
Output:         - Session tersimpan di Neonize session database
                - Session metadata tersimpan di application database

Processing:
  1. Setelah autentikasi sukses, Neonize menyimpan credentials secara internal
  2. Application menyimpan metadata ke sessions table:
     - id, phone_number, status="connected", created_at, last_connected_at
  
Validation:
  - phone_number harus dalam format E.164 (tanpa +): "628xxxx"
  - id harus UUID v4

Test Case: TEST-SESSION-002
```

---

#### SRS-FR-003: Automatic Reconnect

```
Requirement:    FR-003, FR-006 (dari PRD)
Priority:       Must Have

Trigger:        DisconnectedEv diterima dari Neonize

Processing:
  1. SessionDisconnected domain event dipublish
  2. session.status diupdate ke RECONNECTING
  3. Delay = min(2^attempt * 1s, 60s)  [exponential backoff, max 60s]
  4. Attempt reconnect dengan saved session
  5. Success → SessionConnected event, status = CONNECTED, attempts = 0
  6. Failure → attempt++, kembali ke step 3
  7. Setelah MAX_RECONNECT_ATTEMPTS (default: 5):
     - Status = FAILED
     - SessionFailed event dipublish
     - Log CRITICAL dengan alasan

Backoff Table:
  attempt 1: wait 1s
  attempt 2: wait 2s
  attempt 3: wait 4s
  attempt 4: wait 8s
  attempt 5: wait 16s → FAILED

Performance:
  - Reconnect berhasil dalam < 30 detik (pada kondisi normal)
```

---

### 3.2 Messaging — Inbound

#### SRS-FR-010: Receive Text Message

```
Requirement:    FR-010 (dari PRD)
Priority:       Must Have

Input:          - MessageEv dari Neonize (WhatsApp message protobuf)
Output:         - MessageReceived domain event dipublish ke EventBus
                - Log entry: level=DEBUG, event="message_received", from=JID, type="text"

Processing:
  1. Neonize callback dipanggil dengan MessageEv
  2. NeonizeGateway.on_message() dipanggil
  3. MessageEv di-map ke IncomingMessage:
     - id: message.Info.ID
     - from_jid: JID(message.Info.MessageSource.Sender)
     - body: message.Message.Conversation (atau ExtendedTextMessage.Text)
     - timestamp: message.Info.Timestamp
     - is_group: message.Info.MessageSource.IsGroup
  4. IncomingMessage dibungkus dalam MessageReceived event
  5. Event dipublish ke EventBus

Validation:
  - Message ID tidak boleh duplikat (idempotency check)
  - JID harus dalam format yang valid

Error Handling:
  - Invalid message format: Log WARNING, skip (jangan crash)
  - Database error saat simpan: Log ERROR, tetap proses (eventual consistency)

Performance:
  - Waktu dari callback Neonize hingga event dipublish: < 50ms
```

---

#### SRS-FR-018: IncomingMessage Normalization

```
Requirement:    FR-018 (dari PRD)
Priority:       Must Have

Input:          - Raw Neonize MessageEv object

Output:         - IncomingMessage value object dengan field:
                  id: MessageID
                  from_jid: JID
                  session_id: SessionID
                  content: TextContent | MediaContent
                  timestamp: datetime
                  is_group: bool
                  reply_to_id: MessageID | None
                  raw_sender_name: str | None

Type Mapping:
  Neonize Type            → Platform Type
  Conversation            → TextContent(body=str)
  ExtendedTextMessage     → TextContent(body=str)
  ImageMessage            → MediaContent(mime_type, file_size, caption)
  VideoMessage            → MediaContent(mime_type, file_size, caption)
  DocumentMessage         → MediaContent(mime_type, file_name, file_size)
  AudioMessage            → MediaContent(mime_type, file_size)
  
Unknown types: Log WARNING, skip
```

---

### 3.3 Messaging — Outbound

#### SRS-FR-020: Send Text Message

```
Requirement:    FR-020 (dari PRD)
Priority:       Must Have

Input:          - OutgoingMessage(to_jid: JID, body: str)
                - session_id: SessionID

Precondition:   - Session status = CONNECTED
                - body tidak boleh empty string
                - to_jid harus valid JID format

Processing:
  1. Validation: preconditions dicek
  2. SendMessageUseCase.execute(outgoing_message)
  3. Panggil IMessagingGateway.send_text(to_jid, body)
  4. Neonize kirim pesan ke WhatsApp
  5. Dapatkan message ID dari response
  6. Simpan Message entity ke database (status=SENT)
  7. Publish MessageSent domain event
  8. Return message_id

Output:
  - message_id: MessageID (dari WhatsApp)
  - Log: level=INFO, event="message_sent", to=JID, message_id=str

Error Handling:
  - Session tidak CONNECTED: raise SessionNotConnectedException
  - Empty body: raise ValueError("Message body cannot be empty")
  - Neonize error: raise MessageSendFailedException, retry 1x setelah 500ms
  - DB save failure: Log ERROR (pesan tetap terkirim, eventual consistency)

Performance:
  - Waktu dari execute() hingga MessageSent event: < 500ms (p95)
```

---

### 3.4 Command Routing

#### SRS-FR-030: Prefix-Based Command Parsing

```
Requirement:    FR-030 (dari PRD)
Priority:       Must Have

Input:          - IncomingMessage dengan body string
                - Configured prefix (default: "!")

Output:         - BotCommand | None

Algorithm:
  1. Cek apakah body dimulai dengan prefix
  2. Jika tidak: return None
  3. Strip prefix dari body
  4. Split sisa teks dengan whitespace
  5. parts[0].lower() = command name
  6. parts[1:] = args
  7. Return BotCommand(prefix, name, tuple(args), raw_body)

Examples:
  "!help" → BotCommand(prefix="!", name="help", args=(), raw="!help")
  "!send 628xxx Hello" → BotCommand(prefix="!", name="send", args=("628xxx", "Hello"), raw="...")
  "Hello world" → None
  "!" → None (empty command name)

Edge Cases:
  - Pesan hanya prefix: return None
  - Prefix dalam tengah kalimat (misalnya "Harga !diskon"): return None (harus di awal)
  - Multi-line message: hanya baris pertama yang di-parse untuk command
```

---

#### SRS-FR-032: Command Handler Registration

```
Requirement:    FR-032 (dari PRD)
Priority:       Must Have

Registration Contract:
  router.register(
      command_name="help",        # str, case-insensitive
      handler=HelpCommandHandler(), # implements ICommandHandler
      aliases=["h", "?"],        # optional list[str]
      description="Show help"    # untuk auto-help generation
  )

Handler Interface:
  class ICommandHandler(Protocol):
      async def handle(self, ctx: CommandContext) -> None: ...

CommandContext fields:
  - command: BotCommand
  - session_id: SessionID
  - from_jid: JID
  - incoming_message: IncomingMessage
  - send: Callable[[str], Awaitable[None]]  # convenience method
  - reply: Callable[[str], Awaitable[None]] # reply ke message ini

Execution:
  1. CommandRouter menerima IncomingMessage
  2. Parse → BotCommand
  3. Lookup handler by command.name (case-insensitive)
  4. Buat CommandContext
  5. await handler.handle(ctx)
  6. Publish CommandExecuted event

Error Handling:
  - Handler raises exception: Log ERROR, publish CommandFailed event
  - Handler tidak ada: Publish UnknownCommandReceived event
```

---

### 3.5 Feature Module System

#### SRS-FR-040: Feature Module Interface

```
Requirement:    FR-040 (dari PRD)
Priority:       Must Have

Interface Contract:
  class IFeatureModule(Protocol):
      name: str
      version: str
      
      async def setup(self, container: IContainer) -> None:
          """Dipanggil satu kali saat startup. Register handlers di sini."""
          ...
      
      async def teardown(self) -> None:
          """Dipanggil saat shutdown. Cleanup resources."""
          ...
      
      @property
      def is_enabled(self) -> bool:
          """Apakah module ini aktif."""
          ...

Registration:
  registry.register(SessionFeature())
  registry.register(MessagingFeature())
  registry.register(CommandsFeature())
  registry.register(AIIntegrationFeature(), enabled=config.ai_enabled)
```

---

### 3.6 Configuration

#### SRS-FR-050: Environment Variable Configuration

```
Requirement:    FR-050, FR-052 (dari PRD)
Priority:       Must Have

Required Variables:
  DATABASE_URL          string    Default: "sqlite+aiosqlite:///./data/app.db"
  NEONIZE_SESSION_DB    string    Default: "sqlite:///./data/neonize.db"
  LOG_LEVEL             string    Default: "INFO", Values: DEBUG|INFO|WARNING|ERROR
  BOT_COMMAND_PREFIX    string    Default: "!"
  ENVIRONMENT           string    Default: "development", Values: development|staging|production

Optional Variables (Feature-Specific):
  OPENAI_API_KEY        string    Required jika ai_integration enabled
  GEMINI_API_KEY        string    Required jika menggunakan Gemini
  AI_PROVIDER           string    Default: "openai", Values: openai|gemini|none
  REDIS_URL             string    Default: None, Required jika menggunakan ARQ
  MAX_RECONNECT_ATTEMPTS int     Default: 5
  RECONNECT_BACKOFF_MAX  int     Default: 60 (seconds)
  MESSAGE_RETENTION_DAYS int     Default: 90

Validation Rules (di startup):
  - DATABASE_URL harus valid connection string
  - LOG_LEVEL harus salah satu dari valid values
  - ENVIRONMENT harus salah satu dari valid values
  - Jika AI_PROVIDER != "none", API key yang sesuai HARUS ada
  - Jika ada REDIS_URL, harus valid URL format

Fail-Fast Behavior:
  - Jika validasi gagal: log ERROR yang deskriptif, exit dengan code 2
  - Contoh error: "Missing required config: OPENAI_API_KEY (required when AI_PROVIDER=openai)"
```

---

## 4. Non-Functional Requirements — Spesifikasi Detail

### 4.1 Performance Budgets

| Operation | Target (p50) | Target (p95) | Max (p99) |
|-----------|-------------|-------------|----------|
| Neonize callback → EventBus dispatch | < 10ms | < 50ms | < 100ms |
| EventBus → Handler execution (text) | < 50ms | < 200ms | < 500ms |
| Send text message (gateway) | < 200ms | < 500ms | < 1000ms |
| DB write (message save) | < 20ms | < 100ms | < 200ms |
| Command parsing | < 1ms | < 5ms | < 10ms |

### 4.2 Memory Constraints

```
Platform idle (no messages):    < 128 MB RSS
Platform active (100 msg/min):  < 256 MB RSS
Memory leak check interval:     Monitor setiap 5 menit
Memory leak threshold:          RSS growth > 50MB dalam 1 jam tanpa load → ALERT
```

---

## 5. Interface Specifications

### 5.1 Internal Interface: `IMessagingGateway`

```python
class IMessagingGateway(Protocol):
    async def send_text(self, to: JID, body: str) -> MessageID: ...
    async def send_image(self, to: JID, image: bytes, caption: str | None) -> MessageID: ...
    async def send_document(self, to: JID, data: bytes, filename: str, mime: str) -> MessageID: ...
    async def send_audio(self, to: JID, audio: bytes, ptt: bool = False) -> MessageID: ...
    async def reply_text(self, to: JID, reply_to: MessageID, body: str) -> MessageID: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    
    @property
    def is_connected(self) -> bool: ...
```

### 5.2 Internal Interface: `IEventBus`

```python
class IEventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None: ...
    def unsubscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None: ...
```

---

## 6. Error Classification

| Level | Code Format | Example | Action |
|-------|-------------|---------|--------|
| CRITICAL | SYS-001 | Database unavailable at startup | Fail fast, exit |
| ERROR | SES-001 | Session authentication failed | Log, retry/notify |
| ERROR | MSG-001 | Message send failed after retry | Log, emit event |
| WARNING | CMD-001 | Unknown command received | Log, send user feedback |
| WARNING | VAL-001 | Invalid message format received | Log, skip |
| INFO | EVT-001 | Message received/sent | Normal log |
| DEBUG | INT-001 | Internal processing steps | Development only |

---

## 7. Traceability Matrix

| SRS ID | PRD FR | Use Case | Test ID | Handler/UseCase |
|--------|--------|----------|---------|-----------------|
| SRS-FR-001 | FR-001 | UC-001 | TEST-SES-001 | SessionFeature |
| SRS-FR-002 | FR-002 | UC-001 | TEST-SES-002 | SQLAlchemySessionRepo |
| SRS-FR-003 | FR-003, FR-006 | UC-010 | TEST-SES-010 | ReconnectManager |
| SRS-FR-010 | FR-010 | UC-002 | TEST-MSG-001 | NeonizeGateway |
| SRS-FR-018 | FR-018 | UC-002 | TEST-MSG-002 | MessageNormalizer |
| SRS-FR-020 | FR-020 | UC-003 | TEST-MSG-010 | SendMessageUseCase |
| SRS-FR-030 | FR-030 | UC-005 | TEST-CMD-001 | CommandParserService |
| SRS-FR-032 | FR-032 | UC-005 | TEST-CMD-002 | CommandRouter |
| SRS-FR-040 | FR-040 | UC-009 | TEST-CORE-001 | FeatureRegistry |
| SRS-FR-050 | FR-050, FR-052 | — | TEST-CFG-001 | Settings |

---

## References

- [DOC-004: PRD](./04_prd.md)
- [DOC-008: Domain Model](./08_domain_model.md)
- [DOC-013: API Contract](./11_api_contract.md)
- [DOC-020: Testing Strategy](./18_testing_strategy.md)
