# DOC-007 · Architectural Decision Records (ADRs)

> **Status:** Living Document  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Architect  

---

## Apa itu ADR?

ADR (Architectural Decision Record) adalah dokumen pendek yang merekam **satu keputusan arsitektural yang signifikan** beserta konteks dan konsekuensinya. Format: **Konteks → Keputusan → Konsekuensi**.

**Aturan ADR:**
1. Setiap keputusan teknis non-trivial HARUS dicatat sebagai ADR.
2. ADR yang sudah `Accepted` TIDAK boleh diedit — buat ADR baru yang me-supersede-nya.
3. Nomor ADR bersifat sequential dan permanen.

---

## Daftar ADR

| ID | Judul | Status | Tanggal |
|----|-------|--------|---------|
| [ADR-001](./adr/ADR-001_clean_architecture.md) | Menggunakan Clean Architecture + Feature-Based Structure | Accepted | 2026-08-03 |
| [ADR-002](./adr/ADR-002_async_first.md) | Async-First dengan asyncio | Accepted | 2026-08-03 |
| [ADR-003](./adr/ADR-003_neonize_adapter.md) | Neonize sebagai Infrastructure via Adapter Pattern | Accepted | 2026-08-03 |
| [ADR-004](./adr/ADR-004_manual_di.md) | Manual Dependency Injection untuk MVP | Accepted | 2026-08-03 |
| [ADR-005](./adr/ADR-005_session_storage.md) | Session Storage Strategy | Accepted | 2026-08-03 |
| [ADR-006](./adr/ADR-006_event_bus.md) | In-Memory Event Bus untuk Internal Events | Accepted | 2026-08-03 |
| [ADR-007](./adr/ADR-007_sqlalchemy_2.md) | SQLAlchemy 2.x sebagai ORM | Accepted | 2026-08-03 |
| [ADR-008](./adr/ADR-008_uv_package_manager.md) | uv sebagai Package Manager | Accepted | 2026-08-03 |

---

# ADR-002 · Async-First dengan asyncio

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Neonize menggunakan model event-driven yang sangat cocok untuk async programming. Platform perlu menangani banyak event konkuren (pesan masuk, reconnect, task queue, dll).

## Decision

Seluruh codebase menggunakan **async/await** sebagai default. Semua I/O operations bersifat async. CPU-intensive operations menggunakan `asyncio.to_thread()`.

## Consequences

**Positif:**
- Throughput tinggi dengan single thread (event loop)
- Konsisten dengan Neonize async API
- Tidak ada threading complexity

**Negatif:**
- Developer perlu memahami async patterns
- CPU-bound code harus secara eksplisit di-offload

## Rule

```python
# BENAR
async def send_message(self, message: OutgoingMessage) -> None: ...

# SALAH - jangan pernah blokir event loop
def send_message(self, message: OutgoingMessage) -> None:
    time.sleep(1)  # Ini memblokir semua coroutine lain!
```

---

# ADR-003 · Neonize sebagai Infrastructure via Adapter Pattern

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Neonize adalah library pihak ketiga yang bisa berubah API-nya. Business logic tidak boleh bergantung langsung padanya.

## Decision

Neonize **hanya diakses** melalui `NeonizeGateway` yang mengimplementasikan `IMessagingGateway` interface. Tidak ada import Neonize di luar folder `infrastructure/neonize/`.

## Consequences

**Positif:**
- Jika Neonize breaking changes, hanya `NeonizeGateway` yang perlu diupdate
- Business logic bisa di-test dengan `MockMessagingGateway`
- Bisa mengganti Neonize dengan library lain tanpa refactor use case

**Negatif:**
- Sedikit lebih banyak boilerplate untuk mapping types

## Rule

```python
# BENAR - di application layer
from whatsapp_platform.application.interfaces import IMessagingGateway

class SendMessageUseCase:
    def __init__(self, gateway: IMessagingGateway) -> None: ...

# SALAH - jangan pernah import Neonize di luar infrastructure/
from neonize import NewAClient  # Hanya boleh di infrastructure/neonize/
```

---

# ADR-004 · Manual Dependency Injection untuk MVP

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Perlu strategi DI yang clean dan mudah dipahami. Pilihan antara manual DI vs framework DI (dependency-injector, lagom, dishka).

## Decision

Menggunakan **manual DI** dengan `container.py` sebagai pusat konfigurasi untuk MVP. Framework DI dapat dipertimbangkan di v1.0.0 jika kompleksitas meningkat.

## Rationale

- Manual DI lebih mudah di-debug (tidak ada magic)
- Explicit over implicit — setiap dependensi terlihat jelas
- Tidak menambah dependency baru yang perlu dipelajari
- Cukup untuk ukuran project ini

## Consequences

**Positif:**
- Mudah dipahami oleh developer baru
- Tidak ada magic wiring

**Negatif:**
- Lebih verbose untuk project yang sangat besar
- Belum ada scope management otomatis (harus manual)

---

# ADR-005 · Session Storage Strategy

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Neonize session data perlu disimpan secara persistent agar tidak perlu re-scan QR setiap restart. Ada beberapa opsi storage.

## Decision

- **Development**: SQLite via Neonize built-in (`sqlite:///./data/neonize_session.db`)
- **Production**: PostgreSQL via Neonize database support

Metadata session tambahan (status, created_at, dll) disimpan terpisah di database aplikasi (SQLAlchemy).

## Consequences

**Positif:**
- Zero setup untuk development (SQLite built-in)
- Production-ready dengan PostgreSQL
- Neonize mengelola format internal session secara otomatis

**Negatif:**
- Dua database connection di production (session Neonize + app DB) — bisa dikonsolidasi ke satu PostgreSQL

---

# ADR-006 · In-Memory Event Bus untuk Internal Events

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Platform butuh mekanisme pub/sub internal untuk decoupling antar komponen. Pilihan: in-memory vs external message broker (Redis, RabbitMQ).

## Decision

**MVP**: In-memory event bus (`InMemoryEventBus`) yang berjalan di dalam satu proses.

**Future (v1.x)**: Bisa di-swap ke Redis Streams atau RabbitMQ jika butuh multi-process/multi-instance.

## Rationale

- In-memory cukup untuk single-instance platform
- Implementasi minimal, zero external dependency
- Interface `IEventBus` memastikan mudah diganti

## Consequences

**Positif:**
- Zero setup, zero latency overhead
- Mudah di-test

**Negatif:**
- Event hilang jika process crash (not durable)
- Tidak bisa di-share antar process

---

# ADR-007 · SQLAlchemy 2.x sebagai ORM

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Perlu ORM yang mendukung async, type-safe, dan mature.

## Decision

Menggunakan **SQLAlchemy 2.x** dengan async session (`AsyncSession`).

## Rationale

- SQLAlchemy 2.x memiliki full async support
- Type stubs tersedia (mypy strict compatible)
- Paling mature dan battle-tested dari semua pilihan
- Alembic (migration) terintegrasi sempurna

## Alternatives Considered

| Alternatif | Alasan Tidak Dipilih |
|------------|---------------------|
| Tortoise ORM | Community lebih kecil, mypy support kurang |
| SQLModel | Masih beta untuk beberapa fitur |
| raw asyncpg | Terlalu low-level, tidak ada ORM features |

---

# ADR-008 · uv sebagai Package Manager

> **Status:** Accepted | **Date:** 2026-08-03

## Context

Perlu package manager yang modern, cepat, dan mendukung workflow yang clean.

## Decision

Menggunakan **uv** untuk:
- Virtual environment management
- Dependency installation
- Lockfile generation (`uv.lock`)
- Running scripts (`uv run`)

## Rationale

- 10-100x lebih cepat dari pip
- Native support untuk `pyproject.toml`
- Built-in lockfile (deterministik, reproducible builds)
- Single tool menggantikan pip + venv + pip-compile

## Consequences

**Positif:**
- Developer experience jauh lebih baik
- CI lebih cepat
- Reproducible environments

**Negatif:**
- Developer perlu install `uv` terlebih dahulu (satu langkah extra)
- Relatif baru — tapi dikembangkan oleh Astral (tim Ruff) yang sangat aktif

---

## Template untuk ADR Baru

```markdown
# ADR-XXX · [Judul Keputusan]

> **Status:** [Proposed | Accepted | Deprecated | Superseded by ADR-YYY]
> **Date:** YYYY-MM-DD
> **Deciders:** [Nama / Role]

## Context
[Apa situasi yang memerlukan keputusan ini?]

## Decision
[Keputusan apa yang diambil?]

## Rationale
[Mengapa keputusan ini diambil?]

## Consequences
**Positif:**
- ...

**Negatif:**
- ...

## Alternatives Considered
| Alternatif | Alasan Tidak Dipilih |
|------------|---------------------|
| ... | ... |
```
