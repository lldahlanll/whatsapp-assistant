# DOC-015 · Error Handling & Exception Strategy

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Developer + QA Engineer  

---

## 1. Prinsip Error Handling

1. **Fail fast at startup**: Konfigurasi invalid → exit dengan pesan yang jelas
2. **Never swallow exceptions silently**: Selalu log, minimal sebagai WARNING
3. **Recover where possible**: Retry idempotent operations
4. **Degrade gracefully**: Jika fitur gagal, fitur lain harus tetap berjalan
5. **User-friendly errors**: Error yang terlihat user harus informatif, bukan stack trace
6. **Developer-friendly logs**: Internal logs harus mengandung full context

---

## 2. Exception Hierarchy

```python
# src/domain/exceptions.py

class PlatformException(Exception):
    """Base exception untuk semua platform errors."""
    code: str = "PLATFORM_ERROR"
    http_status: int = 500  # Untuk future REST API layer
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

# =============================================================================
# SESSION EXCEPTIONS
# =============================================================================

class SessionException(PlatformException):
    """Base untuk semua session-related errors."""

class SessionNotFoundException(SessionException):
    code = "SESSION_NOT_FOUND"
    http_status = 404

class SessionAlreadyConnectedException(SessionException):
    code = "SESSION_ALREADY_CONNECTED"
    http_status = 409

class SessionNotConnectedException(SessionException):
    code = "SESSION_NOT_CONNECTED"
    http_status = 503
    
    def __init__(self) -> None:
        super().__init__("WhatsApp session is not connected. Please check connection.")

class SessionAuthenticationFailedException(SessionException):
    code = "SESSION_AUTH_FAILED"

class MaxReconnectAttemptsException(SessionException):
    code = "SESSION_MAX_RECONNECT"

class InvalidSessionTransitionException(SessionException):
    code = "SESSION_INVALID_TRANSITION"
    
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Invalid session transition: {from_status} -> {to_status}"
        )

# =============================================================================
# MESSAGING EXCEPTIONS
# =============================================================================

class MessagingException(PlatformException):
    """Base untuk semua messaging-related errors."""

class MessageSendFailedException(MessagingException):
    code = "MESSAGE_SEND_FAILED"
    
    def __init__(self, to_jid: str, reason: str) -> None:
        super().__init__(
            f"Failed to send message to {to_jid}: {reason}",
            details={"to_jid": to_jid, "reason": reason}
        )

class InvalidJIDException(MessagingException):
    code = "INVALID_JID"
    
    def __init__(self, jid: str) -> None:
        super().__init__(f"Invalid JID format: {jid}")

class MessageTooLongException(MessagingException):
    code = "MESSAGE_TOO_LONG"
    
    def __init__(self, length: int, max_length: int) -> None:
        super().__init__(
            f"Message too long: {length} chars (max: {max_length})"
        )

class MediaSizeExceededException(MessagingException):
    code = "MEDIA_SIZE_EXCEEDED"

# =============================================================================
# COMMAND EXCEPTIONS
# =============================================================================

class CommandException(PlatformException):
    """Base untuk semua command-related errors."""

class CommandExecutionException(CommandException):
    code = "COMMAND_EXECUTION_FAILED"

class CommandPermissionDeniedException(CommandException):
    code = "COMMAND_PERMISSION_DENIED"
    
    def __init__(self, command: str, required_role: str) -> None:
        super().__init__(
            f"Permission denied for command '{command}'. Required role: {required_role}"
        )

class CommandNotFoundException(CommandException):
    code = "COMMAND_NOT_FOUND"

# =============================================================================
# CONFIGURATION EXCEPTIONS
# =============================================================================

class ConfigurationException(PlatformException):
    """Base untuk konfigurasi errors."""
    code = "CONFIGURATION_ERROR"

class MissingConfigurationException(ConfigurationException):
    code = "MISSING_CONFIGURATION"
    
    def __init__(self, key: str, hint: str = "") -> None:
        msg = f"Required configuration missing: {key}"
        if hint:
            msg += f". Hint: {hint}"
        super().__init__(msg)

# =============================================================================
# AI EXCEPTIONS
# =============================================================================

class AIException(PlatformException):
    """Base untuk AI provider errors."""

class AIProviderException(AIException):
    code = "AI_PROVIDER_ERROR"

class AIProviderUnavailableException(AIException):
    code = "AI_PROVIDER_UNAVAILABLE"

class AIRateLimitException(AIException):
    code = "AI_RATE_LIMIT"
    
    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__("AI provider rate limit exceeded")
        self.retry_after = retry_after

# =============================================================================
# INFRASTRUCTURE EXCEPTIONS
# =============================================================================

class InfrastructureException(PlatformException):
    """Base untuk infrastructure errors."""

class DatabaseException(InfrastructureException):
    code = "DATABASE_ERROR"

class DatabaseConnectionException(DatabaseException):
    code = "DATABASE_CONNECTION_FAILED"
```

---

## 3. Error Code Reference

| Code | Category | Severity | Retry? |
|------|----------|----------|--------|
| `SESSION_NOT_CONNECTED` | Session | ERROR | Yes — trigger reconnect |
| `SESSION_AUTH_FAILED` | Session | CRITICAL | No |
| `SESSION_MAX_RECONNECT` | Session | CRITICAL | No |
| `MESSAGE_SEND_FAILED` | Messaging | ERROR | Yes (1x, 500ms delay) |
| `INVALID_JID` | Messaging | WARNING | No |
| `MESSAGE_TOO_LONG` | Messaging | WARNING | No — truncate or reject |
| `COMMAND_EXECUTION_FAILED` | Command | ERROR | No |
| `COMMAND_PERMISSION_DENIED` | Command | WARNING | No |
| `MISSING_CONFIGURATION` | Config | CRITICAL | No — fail fast |
| `AI_RATE_LIMIT` | AI | WARNING | Yes (with backoff) |
| `AI_PROVIDER_UNAVAILABLE` | AI | ERROR | Yes |
| `DATABASE_CONNECTION_FAILED` | Infra | CRITICAL | No — fail fast at startup |

---

## 4. Retry Strategy

### 4.1 Idempotent Operations (safe to retry)
- `send_text()`, `send_image()` — retry 1x setelah 500ms
- LLM API calls — retry 2x dengan exponential backoff (1s, 2s)
- Database reads — retry 2x dengan backoff (100ms, 300ms)

### 4.2 Non-Idempotent Operations (DO NOT retry)
- Session authentication
- Database writes (gunakan upsert untuk idempotency)

### 4.3 Retry Implementation

```python
from functools import wraps
import asyncio

async def with_retry(
    fn,
    max_attempts: int = 2,
    backoff_seconds: float = 0.5,
    exceptions: tuple[type[Exception], ...] = (Exception,)
):
    """Generic retry decorator untuk async functions."""
    last_exception = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(backoff_seconds * (2 ** attempt))
    raise last_exception
```

---

## 5. Error Handling Per Layer

### 5.1 Domain Layer
- Raise domain exceptions (pure, no logging)
- Domain exceptions = business rule violations

### 5.2 Application Layer (Use Cases)
- Catch domain exceptions, tambahkan context
- Log pada level yang sesuai
- Emit domain events untuk failures (e.g., `MessageFailed` event)

```python
class SendMessageUseCase:
    async def execute(self, message: OutgoingMessage) -> MessageID:
        try:
            message_id = await self._gateway.send_text(message.to_jid, message.body)
            await self._message_repo.save(Message(..., status=MessageStatus.SENT))
            await self._event_bus.publish(MessageSent(...))
            return message_id
        except MessageSendFailedException as e:
            logger.error("message_send_failed", 
                        to_jid=str(message.to_jid), 
                        error=str(e),
                        code=e.code)
            await self._event_bus.publish(MessageFailed(...))
            raise  # Re-raise agar caller bisa handle
        except DatabaseException as e:
            # Pesan tetap terkirim, tapi DB gagal — log dan continue
            logger.error("message_db_save_failed", message_id=message_id, error=str(e))
            # Tidak re-raise — eventual consistency
            return message_id
```

### 5.3 Infrastructure Layer (Gateway)
- Translate library exceptions ke domain exceptions
- Log technical details pada level DEBUG

```python
class NeonizeGateway:
    async def send_text(self, to: JID, body: str) -> MessageID:
        try:
            result = await self._client.send_message(str(to), body)
            return result.ID
        except Exception as e:  # Neonize exceptions
            logger.debug("neonize_send_error", raw_error=str(e), to=str(to))
            raise MessageSendFailedException(str(to), str(e)) from e
```

### 5.4 Feature Layer (Command Handlers)
- Catch exceptions dari use cases
- Kirim user-friendly error message
- TIDAK boleh let exceptions propagate ke event bus

```python
class CommandRouter:
    async def _execute_handler(self, handler: ICommandHandler, ctx: CommandContext) -> None:
        try:
            start = time.monotonic()
            await handler.handle(ctx)
            duration = (time.monotonic() - start) * 1000
            await self._event_bus.publish(CommandExecuted(
                ..., success=True, execution_time_ms=duration
            ))
        except CommandPermissionDeniedException:
            await ctx.reply("⛔ Anda tidak memiliki izin untuk command ini.")
        except CommandExecutionException as e:
            logger.error("command_execution_failed", command=ctx.command.name, error=str(e))
            await ctx.reply("❌ Terjadi kesalahan. Silakan coba lagi.")
            await self._event_bus.publish(CommandExecuted(
                ..., success=False, error_message=str(e)
            ))
        except Exception as e:
            # Unexpected error — log dan kirim generic message
            logger.exception("unexpected_command_error", command=ctx.command.name)
            await ctx.reply("❌ Terjadi kesalahan yang tidak terduga.")
```

---

## 6. Startup Error Handling (Fail-Fast)

```python
async def startup() -> None:
    """Platform startup dengan fail-fast validation."""
    
    # 1. Load dan validasi config
    try:
        settings = Settings()
    except ValidationError as e:
        print(f"CRITICAL: Invalid configuration:\n{e}")
        sys.exit(2)
    
    # 2. Test database connection
    try:
        await db.connect()
    except DatabaseConnectionException as e:
        logger.critical("database_connection_failed", error=str(e))
        sys.exit(1)
    
    # 3. Run migrations
    try:
        await run_migrations()
    except Exception as e:
        logger.critical("migration_failed", error=str(e))
        sys.exit(1)
```

---

## 7. User-Facing Error Messages

Semua pesan error yang dikirim ke WhatsApp user harus:
- Dalam Bahasa yang natural (sesuai konteks deployment)
- Tidak mengekspos technical details (stack trace, SQL, dll)
- Memberikan saran tindakan selanjutnya bila memungkinkan

| Scenario | User Message |
|----------|-------------|
| Unknown command | "❓ Command `!{name}` tidak dikenal. Ketik `!help` untuk daftar command." |
| Command error | "❌ Gagal menjalankan command. Silakan coba lagi." |
| Permission denied | "⛔ Anda tidak memiliki akses untuk command ini." |
| AI unavailable | "🤖 AI assistant sedang tidak tersedia. Silakan coba beberapa saat lagi." |
| Rate limit | "⏳ Terlalu banyak request. Silakan tunggu sebentar." |

---

## References

- [DOC-008: Domain Model](./08_domain_model.md)
- [DOC-021: Observability](./19_observability.md)
- [DOC-020: Testing Strategy](./18_testing_strategy.md)
