# DOC-006 · Technology Stack Decision Document

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Senior Software Architect + Senior Python Engineer  

---

## Prinsip Pemilihan Teknologi

1. **Proven over trendy** — Pilih teknologi yang sudah terbukti di production, bukan yang hype.
2. **Simplicity first** — Jika ada dua pilihan dengan kemampuan setara, pilih yang lebih sederhana.
3. **Explicit over magic** — Lebih suka library yang transparan daripada yang terlalu "magical".
4. **Community & maintenance** — Pastikan library aktif di-maintain dan memiliki komunitas.

---

## Stack Lengkap

---

### 1. Core Runtime

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Programming Language | Python | 3.13+ | ✅ Final |
| Package Manager | uv | latest | ✅ Final |
| Build System | pyproject.toml (PEP 517) | — | ✅ Final |

#### Mengapa Python 3.13+?
- **`type` statement**: Syntax baru untuk type aliases (`type JID = str`)
- **Improved error messages**: Lebih mudah debug
- **Performance improvements**: GIL improvements, free-threaded mode experimental
- **asyncio improvements**: Lebih stabil dan performant

#### Mengapa `uv` (bukan pip/poetry/pipenv)?
- 10-100x lebih cepat dari pip
- Drop-in replacement untuk pip + virtualenv
- Native lockfile support
- Dikembangkan oleh Astral (sama dengan Ruff)
- Single binary, tidak perlu instalasi tambahan

---

### 2. WhatsApp Integration

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| WhatsApp Library | Neonize | latest stable (pinned) | ✅ Final |

#### Mengapa Neonize?
- Python-native dengan Go backend (Whatsmeow) untuk performance
- Tidak butuh Node.js, browser automation, atau Selenium
- Mendukung async natively (`NewAClient`)
- SQLite + PostgreSQL support untuk session storage
- Aktif di-maintain
- End-to-end encryption built-in

#### Risiko & Mitigasi
- **Risiko**: Breaking changes antar versi
- **Mitigasi**: `IMessagingGateway` interface layer — jika Neonize berubah, hanya adapter yang perlu diupdate, bukan business logic

---

### 3. Database & Persistence

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| ORM | SQLAlchemy | 2.x (async) | ✅ Final |
| Migration | Alembic | latest | ✅ Final |
| DB (Development) | SQLite | built-in | ✅ Final |
| DB (Production) | PostgreSQL | 16+ | ✅ Final |
| Async DB Driver (SQLite) | aiosqlite | latest | ✅ Final |
| Async DB Driver (Postgres) | asyncpg | latest | ✅ Final |

#### Mengapa SQLAlchemy 2.x?
- **Async first**: Native `async_sessionmaker`, `AsyncSession`
- **Type-safe**: Full mypy support dengan stubs
- **Mature**: Battle-tested di production selama 15+ tahun
- **ORM + Core**: Bisa pakai ORM atau raw SQL sesuai kebutuhan
- **Version 2.x**: API yang jauh lebih bersih dari 1.x

#### Alternatif yang Dipertimbangkan
| Alternatif | Alasan Tidak Dipilih |
|------------|---------------------|
| Tortoise ORM | Kurang mature, smaller community |
| Databases (encode) | Terlalu low-level, maintenance kurang aktif |
| Peewee | Tidak async-native |
| Piccolo | Menarik tapi community lebih kecil |

---

### 4. Configuration Management

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Settings | Pydantic Settings | 2.x | ✅ Final |
| Env File Support | python-dotenv (via Pydantic) | built-in | ✅ Final |

#### Mengapa Pydantic Settings?
- **Validation otomatis**: Env vars di-parse dan di-validate saat startup (fail-fast)
- **Type-safe**: Konfigurasi memiliki full type hints
- **Nested settings**: Mudah group konfigurasi per domain
- **Secret support**: `SecretStr` untuk nilai sensitif yang tidak di-log
- **Multiple sources**: Env vars, `.env` file, JSON file

```python
# Contoh konseptual
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./data/session.db"
    neonize_log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"
    openai_api_key: SecretStr | None = None
    
    class Config:
        env_file = ".env"
```

---

### 5. Async Task Queue

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Task Queue | ARQ | latest | ✅ Final (MVP) |
| Message Broker | Redis | 7.x | ✅ Final (bila digunakan) |

#### Mengapa ARQ (bukan Celery)?
| Kriteria | ARQ | Celery |
|----------|-----|--------|
| Async-native | ✅ Ya | ❌ Terbatas |
| Python typing | ✅ Sangat baik | ⚠️ Kurang |
| Dependency | Redis saja | Redis/RabbitMQ + backend |
| Complexity | Rendah | Tinggi |
| Performance | Tinggi | Sedang |
| Documentation | Cukup | Sangat lengkap |

**Catatan**: Untuk MVP, heavy processing menggunakan `asyncio.to_thread()`. ARQ diperkenalkan hanya jika dibutuhkan.

---

### 6. Logging

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Structured Logger | structlog | latest | ✅ Final |
| Format | JSON (production), Console (dev) | — | ✅ Final |

#### Mengapa structlog?
- **Structured by default**: Output JSON yang machine-readable
- **Context binding**: Mudah menambah correlation_id ke semua log dalam satu request
- **Async-friendly**: Tidak ada thread-local hack
- **Rich dev experience**: Pretty print dengan warna di development

---

### 7. Type Checking & Linting

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Linter + Formatter | Ruff | latest | ✅ Final |
| Type Checker | Mypy | latest | ✅ Final |
| Type Stubs | types-* packages | auto | ✅ Final |

#### Mypy Configuration (strict mode)
```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_any_generics = true
```

#### Ruff Rules yang Diaktifkan
```toml
[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings  
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "ANN", # annotations
    "S",   # bandit (security)
    "N",   # pep8-naming
    "PT",  # pytest style
]
```

---

### 8. Testing

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Test Runner | pytest | 8.x | ✅ Final |
| Async Tests | pytest-asyncio | latest | ✅ Final |
| Mocking | pytest-mock + unittest.mock | latest | ✅ Final |
| Coverage | pytest-cov | latest | ✅ Final |
| Test Factories | factory-boy | latest | ✅ Final |
| Fake HTTP | respx (httpx-based) | latest | ✅ Final |

---

### 9. DevOps & Infrastructure

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| Containerization | Docker | latest | ✅ Final |
| Local Orchestration | Docker Compose | v2 | ✅ Final |
| CI/CD | GitHub Actions | — | ✅ Final |
| Pre-commit Hooks | pre-commit | latest | ✅ Final |
| Secret Scanning | truffleHog / gitleaks | CI | ✅ Final |
| Dependency Scanning | pip-audit | CI | ✅ Final |

---

### 10. Documentation

| Item | Pilihan | Versi | Status |
|------|---------|-------|--------|
| API Docs Generator | MkDocs + mkdocstrings | latest | ✅ Final |
| Theme | Material for MkDocs | latest | ✅ Final |
| Diagram Format | Mermaid (in Markdown) | — | ✅ Final |
| Changelog Generator | git-cliff | latest | ✅ Final |

---

## Dependency Summary (`pyproject.toml` preview)

```toml
[project]
name = "whatsapp-platform"
version = "0.1.0"
requires-python = ">=3.13"

dependencies = [
    "neonize>=0.x.x",          # WhatsApp integration
    "sqlalchemy[asyncio]>=2.0", # ORM
    "alembic>=1.13",            # DB migrations
    "aiosqlite>=0.19",          # SQLite async driver
    "asyncpg>=0.29",            # PostgreSQL async driver
    "pydantic-settings>=2.0",   # Configuration
    "structlog>=24.0",          # Structured logging
    "arq>=0.25",                # Async task queue (optional)
]

[project.optional-dependencies]
ai = [
    "openai>=1.0",              # OpenAI integration
    "google-generativeai>=0.5", # Gemini integration
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pytest-mock>=3.12",
    "factory-boy>=3.3",
    "mypy>=1.10",
    "ruff>=0.4",
    "pre-commit>=3.7",
]
```

---

## Version Pinning Strategy

- **Neonize**: Pin ke exact version (`==x.y.z`) karena potensi breaking changes tinggi
- **SQLAlchemy**: Pin ke major version (`>=2.0,<3.0`)
- **Python stdlib-based**: Biarkan float (`>=x.y`)
- **Dev dependencies**: Biarkan float, update berkala

---

## References

- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-007: ADRs](./adr/)
- [DOC-022: CI/CD Pipeline](./20_cicd_pipeline.md)
- [Neonize GitHub](https://github.com/krypton-byte/neonize)
- [uv Documentation](https://docs.astral.sh/uv/)
- [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/en/20/)
- [structlog Docs](https://www.structlog.org/)
