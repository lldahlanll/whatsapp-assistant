# 📘 Developer Handbook: Coding Standards & Best Practices

> **Target Platform:** Python 3.13+ • Neonize • Clean Architecture • Async-First  
> **Status:** Active Standard  
> **Version:** 2.0.0  
> **Last Updated:** 2026-08-03  

---

## 📋 Table of Contents

1. [Naming Convention](#1-naming-convention)
2. [Folder Convention](#2-folder-convention)
3. [Module Convention](#3-module-convention)
4. [Function Convention](#4-function-convention)
5. [Class Convention](#5-class-convention)
6. [Dependency Injection](#6-dependency-injection)
7. [Exception Standards](#7-exception-standards)
8. [Logging Standards](#8-logging-standards)
9. [Error Handling](#9-error-handling)
10. [Configuration Management](#10-configuration-management)
11. [Typing & Type Hints](#11-typing--type-hints)
12. [Async Programming Rules](#12-async-programming-rules)
13. [Comment Guidelines](#13-comment-guidelines)
14. [Docstring Standard](#14-docstring-standard)
15. [Import Rules](#15-import-rules)
16. [Testing Rules](#16-testing-rules)
17. [Git Workflow](#17-git-workflow)
18. [Commit Convention](#18-commit-convention)
19. [Branch Naming Convention](#19-branch-naming-convention)
20. [Pull Request (PR) Standard](#20-pull-request-pr-standard)
21. [Code Review Guidelines](#21-code-review-guidelines)

---

## 1. Naming Convention

| Elemen Kode | Format | Contoh |
| :--- | :--- | :--- |
| **Package / Module** | `snake_case` | `session_repository.py`, `whatsapp_platform/` |
| **Class / Struct** | `PascalCase` | `WhatsAppSession`, `SendMessageUseCase` |
| **Interface / Protocol**| Prefix `I` + `PascalCase` | `ISessionRepository`, `IMessagingGateway` |
| **Abstract Base Class** | Prefix `Base` / `Abstract` | `BaseCommandHandler`, `AbstractEventBus` |
| **Function / Method** | `snake_case` | `send_message_async()`, `parse_command()` |
| **Variable** | `snake_case` | `session_id`, `retry_count` |
| **Constant** | `SCREAMING_SNAKE_CASE` | `MAX_RECONNECT_ATTEMPTS = 5` |
| **Enum Class** | `PascalCase` | `MessageStatus(StrEnum)` |
| **Enum Member** | `SCREAMING_SNAKE_CASE` | `MessageStatus.DELIVERED` |
| **Type Alias** | `PascalCase` | `type JID = str`, `type SessionID = str` |
| **Boolean Variable/Fn** | Prefix `is_`, `has_`, `can_` | `is_connected`, `has_permission()` |

```python
# GOOD
type JID = str

class MessageStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"

async def is_session_active(session_id: SessionID) -> bool:
    ...
```

---

## 2. Folder Convention

- Gunakan **`snake_case`** untuk semua folder.
- Pisahkan folder berdasarkan layer Clean Architecture:
  - `src/whatsapp_platform/domain/`: Pure business rules (no external deps).
  - `src/whatsapp_platform/application/`: Orchestration & Use Cases.
  - `src/whatsapp_platform/infrastructure/`: Adapters (Neonize, DB, Redis, OpenAI).
  - `src/whatsapp_platform/presentation/`: Event listeners, REST API, CLI.
  - `src/whatsapp_platform/config/`: App configuration.
  - `src/whatsapp_platform/plugins/`: Modular plugin extensions.
  - `src/whatsapp_platform/shared/`: Helper & utilities.
- Gunakan bentuk jamak (*plural*) untuk folder koleksi: `entities/`, `use_cases/`, `repositories/`, `handlers/`.

---

## 3. Module Convention

- Satu module Python (`.py`) harus memiliki **Single Responsibility** (Satu alasan untuk berubah).
- **Ukuran Maksimal:** Maksimal 200 baris kode per file (guideline). Jika >300 baris, **WAJIB** di-refactor/split.
- Setiap package folder **WAJIB** memiliki file `__init__.py` yang secara eksplisit mengekspos public interface via `__all__`.

```python
# src/whatsapp_platform/domain/value_objects/__init__.py
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_id import MessageID

__all__ = ["JID", "MessageID"]
```

---

## 4. Function Convention

- **Explicit Return Type:** Selalu berikan type annotation pada return value.
- **Max Length:** Maksimal 30 baris kode substantif per fungsi.
- **Max Parameters:** Maksimal 4 parameter. Jika >4, bungkus ke dalam DTO atau Dataclass.
- **Pure Functions:** Diutamakan pada Domain Layer (tanpa side-effects).

```python
# GOOD
async def send_message(
    self,
    dto: OutgoingMessageDTO,  # Mengelompokkan parameter
) -> MessageID:
    ...

# BAD
async def send_message(self, to, body, media_url, is_group, reply_to_id, caption, retry):
    ...
```

---

## 5. Class Convention

- **Dataclasses untuk DTO & Value Objects:** Gunakan `@dataclass(frozen=True)` untuk Immutability.
- **Entities:** Dataclass standar (`frozen=False`) jika membutuhkan mutasi state terenkapsulasi.
- **Interfaces:** Menggunakan `typing.Protocol` atau `abc.ABC` dengan method abstract `@abstractmethod`.
- **Suffix Nama:**
  - Use Case: `SendMessageUseCase`
  - Repository: `SQLAlchemySessionRepository` (impl), `ISessionRepository` (interface)
  - Handler: `MessageReceivedHandler`
  - DTO: `IncomingMessageDTO`

---

## 6. Dependency Injection

- **Constructor Injection:** Pass dependency melalui `__init__` dengan tipe Abstract Interface / Protocol (bukan kelas konkret).
- **Dilarang Global State:** Jangan meng-instantiate singleton global atau memanggil kelas infrastruktur langsung di dalam domain/application layer.
- **DI Container:** Gunakan container Dishka atau framework DI terkonfigurasi.

```python
# GOOD — Constructor Injection via Protocol Interface
class SendMessageUseCase:
    def __init__(
        self,
        messaging_gateway: IMessagingGateway,
        message_repo: IMessageRepository,
    ) -> None:
        self._gateway = messaging_gateway
        self._repo = message_repo
```

---

## 7. Exception Standards

- **Hirarki Custom Exception:** Semua exception aplikasi harus mewarisi base `AppException` atau `DomainException`.
- **Lokasi:** Custom domain exception diletakkan di `domain/exceptions/`.
- **Naming:** Akhiri dengan Suffix `Exception` atau `Error`.
- **Inheritance:** HANYA mewarisi dari `Exception` (DILARANG mewarisi dari `BaseException`).

```python
# domain/exceptions/base.py
class DomainException(Exception):
    """Base class untuk semua domain exceptions."""

class SessionNotConnectedException(DomainException):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"WhatsApp Session '{session_id}' sedang tidak terhubung.")
```

---

## 8. Logging Standards

- **Structured Logging:** Wajib menggunakan **`structlog`** dengan output format JSON di production.
- **Snake Case Event Names:** Parameter pertama `logger.info()` adalah nama event pendek dalam `snake_case`.
- **Dilarang Logging Rahasia:** Jangan pernah mencetak password, token, atau API key.
- **Dilarang `print()`:** Penggunaan `print()` di production code dilarang keras (gunakan `logger`).

```python
# GOOD
logger.info(
    "message_sent_successfully",
    message_id=msg_id,
    recipient_jid=str(to_jid),
    duration_ms=45.2,
)

# BAD
print(f"Sent message {msg_id} to {to_jid}")
logger.info(f"API Key used: {settings.openai_api_key}")  # SECURITY RISK!
```

---

## 9. Error Handling

- **Catch Exception Spesifik:** Selalu tangkap exception tertentu, hindari bare `except:`.
- **Dilarang Swallow Exception:** Jangan tangkap exception hanya untuk di-`pass` tanpa logging atau re-raise.
- **Exception Chaining:** Preserve original traceback menggunakan `raise NewException(...) from e`.

```python
# GOOD
try:
    await self._gateway.send_text(jid, body)
except NeonizeNetworkError as e:
    logger.error("whatsapp_gateway_network_failure", jid=str(jid), error=str(e))
    raise MessageSendFailedException(str(jid), str(e)) from e

# BAD
try:
    await self._gateway.send_text(jid, body)
except Exception:
    pass  # DILARANG!
```

---

## 10. Configuration Management

- Gunakan **Pydantic Settings v2** di `src/whatsapp_platform/config/settings.py`.
- Gunakan `SecretStr` untuk kredensial sensitif.
- Fail-fast: Aplikasi harus crash saat startup jika environment variable utama tidak valid.

```python
class Settings(BaseSettings):
    env: Literal["development", "staging", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./storage/sessions/app.db"
    openai_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

---

## 11. Typing & Type Hints

- **Strict Mode:** Mypy & Pyright dikonfigurasi dalam `strict = true`.
- **Python 3.13 Syntax:**
  - Gunakan `str | None` (bukan `Optional[str]`).
  - Gunakan `list[str]`, `dict[str, int]` (bukan `List`, `Dict`).
  - Gunakan `type JID = str` untuk type alias.
- **Dilarang `Any`:** Hindari penggunaan `typing.Any`. Jika terpaksa, tambahkan penjelasan `# type: ignore[reason]`.

---

## 12. Async Programming Rules

- Semua operasi I/O (Database, Redis, HTTP, Neonize) **WAJIB `async/await`**.
- **Dilarang Blocking I/O:** Dilarang memanggil `time.sleep()` atau synchronous `requests` di dalam async coroutine. Gunakan `asyncio.sleep()` atau `httpx.AsyncClient`.
- **Offload CPU Heavy:** Untuk tugas berat CPU (proses gambar/PDF), gunakan `await asyncio.to_thread(func, *args)`.
- **Async Context Manager:** Gunakan `async with` untuk mengelola resource session/DB connection.

---

## 13. Comment Guidelines

- **Jelaskan *WHY*, Bukan *WHAT*:** Kode harus *self-documenting*. Komentar hanya berisi alasan bisnis di balik keputusan yang tidak eksplisit.
- **Format TODO:** `TODO(username): Deskripsi pekerjaan` atau `FIXME(username): Deskripsi bug`.

```python
# GOOD — Menjelaskan alasan teknis
# Neonize membutuhkan delay minimal 500ms antar broadcast untuk menghindari rate limit WA server.
await asyncio.sleep(0.5)

# BAD — Menjelaskan hal yang sudah jelas dari kode
# Tidur selama 0.5 detik
await asyncio.sleep(0.5)
```

---

## 14. Docstring Standard

Setiap public class, interface, dan public method **WAJIB** memiliki docstring bergaya **Google Style**.

```python
async def execute(self, dto: SendMessageDTO) -> MessageID:
    """Mengirim pesan WhatsApp ke penerima dan menyimpan riwayat pengiriman.

    Args:
        dto: Data Transfer Object berisi JID penerima dan isi pesan.

    Returns:
        MessageID unik yang dikembalikan oleh WhatsApp server.

    Raises:
        SessionNotConnectedException: Jika WhatsApp client tidak dalam status terhubung.
        MessageSendFailedException: Jika pengiriman gagal setelah 3 kali retry.
    """
```

---

## 15. Import Rules

Aturan di-enforce otomatis oleh **Ruff (isort)**:

1. **Standard Library** (`import asyncio`, `from datetime import datetime`)
2. **Third-Party Libraries** (`import structlog`, `from pydantic import BaseModel`)
3. **Internal Packages** (`from whatsapp_platform.domain...`)

- **Absolute Import Only:** Selalu gunakan import absolut dari root package `whatsapp_platform`. Relative import (`from ..domain`) **DILARANG**.
- **Dilarang Wildcard Import:** `from neonize import *` **DILARANG KERAS**.

---

## 16. Testing Rules

- **Target Coverage:** Minimal **80%** test coverage pada domain & application layer.
- **Struktur Test:** Mengikuti arsitektur `tests/unit/`, `tests/integration/`, `tests/e2e/`.
- **AAA Pattern:** Setiap test function harus dibagi menjadi 3 blok jelas: `Arrange`, `Act`, `Assert`.
- **Naming Test File:** Harus berawalan `test_*.py`.

```python
@pytest.mark.asyncio
async def test_send_message_success(mock_gateway, mock_repo):
    # Arrange
    use_case = SendMessageUseCase(mock_gateway, mock_repo)
    dto = SendMessageDTO(to_jid="628123456789@s.whatsapp.net", body="Hello")

    # Act
    result = await use_case.execute(dto)

    # Assert
    assert result is not None
    mock_gateway.send_text.assert_called_once()
```

---

## 17. Git Workflow

- **Trunk-Based / Short-Lived Feature Branches:** Branch utama adalah `main`. Semua pengembangan fitur dilakukan di feature branch pendek dan di-merge melalui PR.
- **Pre-commit Hooks:** Wajib memasang pre-commit hook (`pre-commit install`) sebelum melakukan commit.

---

## 18. Commit Convention

Mengikuti spesifikasi **Conventional Commits**:

Format: `<type>(<scope>): <subject>`

- **Types:**
  - `feat`: Fitur baru untuk pengguna
  - `fix`: Perbaikan bug
  - `docs`: Perubahan dokumentasi
  - `style`: Format kode (tanpa mengubah logika)
  - `refactor`: Refactoring kode tanpa mengubah fitur
  - `test`: Menambah/memperbaiki unit test
  - `chore`: Update build scripts, dependencies, atau tooling
  - `ci`: Perubahan konfigurasi CI/CD

```bash
# Contoh Commit Message
git commit -m "feat(messaging): add retry mechanism for failed media upload"
git commit -m "fix(session): resolve SQLite connection leak on reconnect"
```

---

## 19. Branch Naming Convention

Format: `<type>/<ticket-id>-<short-description>`

Contoh:
- `feat/WA-101-session-reconnection`
- `fix/WA-204-qr-code-rendering`
- `chore/WA-500-update-deps`

---

## 20. Pull Request (PR) Standard

- **Judul PR:** Mengikuti format Conventional Commits.
- **PR Template Checklist:**
  - [ ] Kode sudah di-lint & format dengan `uv run ruff check .`
  - [ ] Type check 100% lolos dengan `uv run mypy src`
  - [ ] Unit & Integration test lulus 100%
  - [ ] Dokumentasi/docstring telah diperbarui jika ada perubahan API
- **Ukuran PR:** Maksimal 400 baris perubahan kode per PR (kecuali autogenerated lockfile).

---

## 21. Code Review Guidelines

- **Reviewer Requirement:** Setiap PR wajib mendapatkan minimal **1 approval** dari Senior Developer sebelum merge.
- **Gunakan Prefix Komentar Review:**
  - `nit:` (Perubahan minor yang tidak wajib)
  - `suggestion:` (Saran alternatif pendekatan kode)
  - `issue:` (Masalah/bug yang harus diperbaiki sebelum merge)
  - `question:` (Pertanyaan klarifikasi)
  - `blocking:` (Pelanggaran arsitektur/keamanan kritis)
- **Fokus Review:** Kepatuhan Clean Architecture (Dependency Rule), Type Safety, Test Coverage, dan Keamanan Data.
