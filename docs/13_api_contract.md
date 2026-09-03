# DOC-013 · API Contract & Interface Specification

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Developer  

---

## 1. Prinsip Interface Design

1. **Interface-First**: Definisikan interface sebelum implementasi
2. **Python Protocol**: Gunakan `typing.Protocol` untuk structural subtyping (lebih fleksibel dari ABC untuk testing)
3. **Async by default**: Semua I/O methods adalah `async def`
4. **Full type hints**: Semua parameter dan return type ter-annotasi lengkap
5. **Explicit over implicit**: Tidak ada `**kwargs` di interface utama

---

## 2. Core Interfaces

### 2.1 `IMessagingGateway`

**Location:** `src/application/interfaces/messaging_gateway.py`

```python
from typing import Protocol
from whatsapp_platform.domain.value_objects import JID, MessageID
from whatsapp_platform.domain.entities import IncomingMessage

class IMessagingGateway(Protocol):
    """
    Contract untuk semua implementasi messaging gateway.
    
    Implementasi konkret: NeonizeGateway (infrastructure/neonize/)
    Mock untuk testing: MockMessagingGateway (tests/mocks/)
    """
    
    async def send_text(self, to: JID, body: str) -> MessageID:
        """
        Kirim pesan teks ke JID yang ditentukan.
        
        Args:
            to: Target JID (personal atau group)
            body: Isi pesan (tidak boleh empty string)
            
        Returns:
            MessageID dari WhatsApp
            
        Raises:
            SessionNotConnectedException: Jika session tidak aktif
            MessageSendFailedException: Jika pengiriman gagal setelah retry
            InvalidJIDException: Jika format JID tidak valid
        """
        ...
    
    async def send_image(
        self, 
        to: JID, 
        image_data: bytes, 
        mime_type: str = "image/jpeg",
        caption: str | None = None
    ) -> MessageID:
        """Kirim pesan gambar."""
        ...
    
    async def send_video(
        self,
        to: JID,
        video_data: bytes,
        mime_type: str = "video/mp4",
        caption: str | None = None
    ) -> MessageID:
        """Kirim pesan video."""
        ...
    
    async def send_document(
        self,
        to: JID,
        document_data: bytes,
        filename: str,
        mime_type: str = "application/octet-stream"
    ) -> MessageID:
        """Kirim dokumen."""
        ...
    
    async def send_audio(
        self,
        to: JID,
        audio_data: bytes,
        mime_type: str = "audio/ogg",
        ptt: bool = False  # push-to-talk (voice note)
    ) -> MessageID:
        """Kirim pesan audio."""
        ...
    
    async def reply_text(
        self,
        to: JID,
        reply_to: MessageID,
        body: str
    ) -> MessageID:
        """Reply ke pesan tertentu dengan teks."""
        ...
    
    async def start(self) -> None:
        """Start gateway, establish connection."""
        ...
    
    async def stop(self) -> None:
        """Graceful shutdown — disconnect tanpa logout."""
        ...
    
    @property
    def is_connected(self) -> bool:
        """True jika session aktif dan terhubung."""
        ...
    
    @property
    def session_id(self) -> str | None:
        """ID session yang sedang aktif."""
        ...
```

---

### 2.2 `IEventBus`

**Location:** `src/application/interfaces/event_bus.py`

```python
from typing import Protocol, TypeVar, Callable, Awaitable
from whatsapp_platform.domain.events import DomainEvent

DomainEventT = TypeVar("DomainEventT", bound=DomainEvent)
EventHandler = Callable[[DomainEvent], Awaitable[None]]

class IEventBus(Protocol):
    """
    Internal pub/sub untuk domain events.
    
    Implementasi konkret: InMemoryEventBus
    Mock untuk testing: MockEventBus (tests/mocks/)
    """
    
    async def publish(self, event: DomainEvent) -> None:
        """
        Publish satu domain event ke semua subscribers.
        
        Handlers dipanggil secara concurrent (asyncio.gather).
        Jika satu handler error, error di-log tapi handler lain tetap dijalankan.
        
        Args:
            event: Domain event yang akan dipublish
        """
        ...
    
    def subscribe(
        self,
        event_type: type[DomainEventT],
        handler: Callable[[DomainEventT], Awaitable[None]]
    ) -> None:
        """
        Subscribe ke event type tertentu.
        
        Args:
            event_type: Class dari event (e.g., MessageReceived)
            handler: Async callable yang akan dipanggil
        """
        ...
    
    def unsubscribe(
        self,
        event_type: type[DomainEventT],
        handler: Callable[[DomainEventT], Awaitable[None]]
    ) -> None:
        """Batalkan subscription."""
        ...
    
    def get_subscriber_count(self, event_type: type[DomainEvent]) -> int:
        """Jumlah subscriber untuk event type tertentu (untuk testing/monitoring)."""
        ...
```

---

### 2.3 `ISessionRepository`

**Location:** `src/domain/repositories/session_repository.py`

```python
from abc import ABC, abstractmethod
from whatsapp_platform.domain.entities import WhatsAppSession
from whatsapp_platform.domain.value_objects import SessionID

class ISessionRepository(ABC):
    """Repository interface untuk WhatsAppSession aggregate."""
    
    @abstractmethod
    async def get_by_id(self, session_id: SessionID) -> WhatsAppSession | None:
        """Ambil session berdasarkan ID. Return None jika tidak ditemukan."""
        ...
    
    @abstractmethod
    async def get_active(self) -> WhatsAppSession | None:
        """Ambil session yang sedang dalam status CONNECTED."""
        ...
    
    @abstractmethod
    async def save(self, session: WhatsAppSession) -> None:
        """Insert atau update session. Idempotent."""
        ...
    
    @abstractmethod
    async def delete(self, session_id: SessionID) -> None:
        """Hapus session (untuk logout)."""
        ...
    
    @abstractmethod
    async def list_all(self) -> list[WhatsAppSession]:
        """List semua session (untuk multi-session di versi depan)."""
        ...
```

---

### 2.4 `IMessageRepository`

**Location:** `src/domain/repositories/message_repository.py`

```python
from abc import ABC, abstractmethod
from whatsapp_platform.domain.entities import Message
from whatsapp_platform.domain.value_objects import MessageID, ConversationID

class IMessageRepository(ABC):
    
    @abstractmethod
    async def save(self, message: Message) -> None:
        """Simpan message. Idempotent berdasarkan message.id."""
        ...
    
    @abstractmethod
    async def get_by_id(self, message_id: MessageID) -> Message | None: ...
    
    @abstractmethod
    async def get_conversation_history(
        self,
        conversation_id: ConversationID,
        limit: int = 50,
        before_id: MessageID | None = None
    ) -> list[Message]:
        """Ambil history pesan (descending by time). before_id untuk pagination."""
        ...
    
    @abstractmethod
    async def update_status(self, message_id: MessageID, status: MessageStatus) -> None:
        """Update hanya status (optimistic, no full entity load)."""
        ...
    
    @abstractmethod
    async def exists(self, message_id: MessageID) -> bool:
        """Cek apakah message ID sudah ada (untuk idempotency check)."""
        ...
```

---

### 2.5 `ICommandHandler`

**Location:** `src/features/commands/base.py`

```python
from typing import Protocol
from whatsapp_platform.features.commands.context import CommandContext

class ICommandHandler(Protocol):
    """
    Interface untuk semua command handlers.
    
    Setiap command handler menangani satu (atau beberapa) bot command.
    """
    
    @property
    def name(self) -> str:
        """Nama handler untuk logging dan registry."""
        ...
    
    @property
    def description(self) -> str:
        """Deskripsi singkat untuk !help command."""
        ...
    
    @property
    def usage(self) -> str:
        """Contoh penggunaan. Contoh: '!ping', '!ask <pertanyaan>'"""
        ...
    
    async def handle(self, ctx: CommandContext) -> None:
        """
        Eksekusi command.
        
        Args:
            ctx: CommandContext berisi command, from_jid, dan helper methods
            
        Raises:
            CommandExecutionException: Jika eksekusi gagal (akan di-catch oleh router)
        """
        ...
```

---

### 2.6 `IFeatureModule`

**Location:** `src/application/interfaces/feature_module.py`

```python
from typing import Protocol

class IFeatureModule(Protocol):
    """
    Interface untuk semua feature modules.
    
    Setiap feature module adalah unit yang bisa ditambahkan/dihapus
    tanpa memengaruhi feature lain.
    """
    
    @property
    def name(self) -> str:
        """Nama unik feature. Digunakan untuk logging dan config."""
        ...
    
    @property
    def version(self) -> str:
        """Versi feature module (semantic versioning)."""
        ...
    
    @property
    def is_enabled(self) -> bool:
        """Apakah feature ini aktif."""
        ...
    
    async def setup(self, container: "IContainer") -> None:
        """
        Inisialisasi feature.
        
        Dipanggil sekali saat startup.
        Di sini: register event handlers, command handlers, dll.
        
        Args:
            container: DI container untuk resolve dependencies
        """
        ...
    
    async def teardown(self) -> None:
        """
        Cleanup resources.
        
        Dipanggil saat shutdown. Harus idempotent.
        """
        ...
```

---

### 2.7 `IAIProvider`

**Location:** `src/features/ai_integration/providers/base.py`

```python
from typing import Protocol, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str

class IAIProvider(Protocol):
    """
    Interface untuk LLM providers.
    
    Implementasi:
    - OpenAIProvider (OpenAI GPT-4, GPT-4o, etc.)
    - GeminiProvider (Google Gemini)
    - NoopAIProvider (dummy, untuk testing/disabled)
    """
    
    @property
    def model_name(self) -> str:
        """Nama model yang digunakan. Contoh: 'gpt-4o-mini'"""
        ...
    
    @property
    def is_available(self) -> bool:
        """True jika provider terkonfigurasi dan tersedia."""
        ...
    
    async def complete(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        """
        Request completion dari LLM.
        
        Args:
            messages: Conversation history dalam format ChatMessage
            max_tokens: Maksimum token response
            temperature: Kreativitas (0.0 = deterministik, 2.0 = sangat kreatif)
            
        Returns:
            Response text dari LLM
            
        Raises:
            AIProviderException: Jika request gagal (timeout, rate limit, dll)
        """
        ...
```

---

## 3. Data Transfer Objects (DTOs)

### 3.1 `CommandContext`

```python
@dataclass
class CommandContext:
    """Context object yang diberikan ke setiap CommandHandler."""
    
    command: BotCommand
    session_id: SessionID
    from_jid: JID
    incoming_message: IncomingMessage
    
    # Convenience methods (di-inject oleh router)
    _send_fn: Callable[[str], Awaitable[None]]
    _reply_fn: Callable[[str], Awaitable[None]]
    
    async def send(self, text: str) -> None:
        """Kirim pesan ke pengirim command."""
        await self._send_fn(text)
    
    async def reply(self, text: str) -> None:
        """Reply ke pesan command yang diterima."""
        await self._reply_fn(text)
    
    @property
    def args(self) -> tuple[str, ...]:
        """Command arguments."""
        return self.command.args
    
    @property
    def sender_jid(self) -> JID:
        """JID dari pengirim command."""
        return self.from_jid
```

---

## 4. Neonize Event Mapping

Pemetaan dari Neonize events ke domain objects platform kita:

| Neonize Event | Domain Event | Mapper Class |
|---------------|-------------|-------------|
| `MessageEv` | `MessageReceived` | `NeonizeMessageMapper` |
| `ReceiptEv` (delivered) | `MessageDelivered` | `NeonizeReceiptMapper` |
| `ReceiptEv` (read) | `MessageRead` | `NeonizeReceiptMapper` |
| `ConnectedEv` | `SessionConnected` | `NeonizeSessionMapper` |
| `DisconnectedEv` | `SessionDisconnected` | `NeonizeSessionMapper` |
| `QREv` | `QRCodeGenerated` | `NeonizeSessionMapper` |
| `PairSuccessEv` | `SessionAuthenticated` | `NeonizeSessionMapper` |

---

## References

- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-008: Domain Model](./08_domain_model.md)
- [DOC-011: SRS](./11_srs.md)
- [DOC-019: DI Strategy](./17_di_strategy.md)
