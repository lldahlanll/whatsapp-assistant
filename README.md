# 🚀 Production-Grade WhatsApp Platform

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Neonize](https://img.shields.io/badge/whatsapp-Neonize-green.svg)](https://github.com/krypton-byte/neonize)
[![Tests: 102 Passed](https://img.shields.io/badge/tests-102%20passed-success.svg)](tests/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Architecture: Clean](https://img.shields.io/badge/architecture-Clean%20%2B%20DDD-orange.svg)](docs/05_architecture_overview.md)

Platform otomasi WhatsApp production-grade berbasis **Python 3.13+** dan **Neonize**. Didesain dengan prinsip **Clean Architecture**, **Domain-Driven Design (DDD)** yang sederhana, **Feature-Based Vertical Slice**, dan full **Async/Type-Safe** programming.

---

## 🌟 Implemented Features & Core Capabilities

- ⚡ **High Performance Async-First**: Menggunakan Python `asyncio` & `NeonizeGateway` (Whatsmeow Go backend adapter).
- 🧩 **Modular Feature Modules**: Registered via `FeatureRegistry` (`SessionFeature`, `MessagingFeature`, `CommandsFeature`).
- 🔒 **Clean Architecture & DDD**: Entities (`Session`, `Message`, `Conversation`, `Contact`), Value Objects (`JID`, `MessageContent`, `BotCommand`), domain events, and repositories interfaces.
- 💾 **SQLite & SQLAlchemy 2.0 Async Persistence**: Automatic Alembic migrations with fully typed async repositories.
- ⚡ **Async Event Bus**: In-memory pub/sub event bus with handler isolation and gateway domain event forwarding.
- 🤖 **Extensible Command Router & Handlers**: Built-in commands (`!ping`, `!help`, `!echo`, `!info`, `!group`) and extensible command router.
- 📄 **Media Processing Engine**: OCR for images, PDF text extractor, and audio transcription pipeline fallback.
- 📱 **QR & Session Lifecycle**: Reconnect otomatis, QR pairing, dan session status tracking (`SessionStatus`).
- 🧪 **102 Automated Tests Passing**: Full unit and integration test suite with high coverage using `pytest`.

---

## 🏗️ Architecture Blueprint

```
+----------------------------------------------------------+
|                   INFRASTRUCTURE LAYER                    |
|  (Neonize Gateway, SQLAlchemy Repos, Config, Loggers)   |
|                                                          |
|   +--------------------------------------------------+   |
|   |              APPLICATION LAYER                   |   |
|   |   (Use Cases, Event Bus, Feature Registry)       |   |
|   |                                                  |   |
|   |   +------------------------------------------+  |   |
|   |   |           DOMAIN LAYER                   |  |   |
|   |   |  (Entities, Value Objects, Domain Events,|  |   |
|   |   |   Repository Contracts, Exceptions)      |  |   |
|   |   +------------------------------------------+  |   |
|   +--------------------------------------------------+   |
+----------------------------------------------------------+
```

---

## ⚡ Quick Start

### Prerequisites
- Python >= 3.13
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (optional)

### Setup & Run Locally

1. **Clone & Setup Environment**
   ```bash
   git clone https://github.com/your-org/whatsapp-platform.git
   cd whatsapp-platform
   uv sync
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   ```

3. **Run Application**
   ```bash
   uv run python -m whatsapp_platform
   ```
   *Scan QR Code yang muncul di terminal menggunakan aplikasi WhatsApp Anda.*

---

## 📚 Complete Project Documentation

Seluruh perancangan software engineering sebelum coding didokumentasikan secara rinci:

| Fase | Dokumen Utama | Link |
|---|---|---|
| **1. Business & Vision** | Product Vision, Glossary, PRD | [Product Vision](docs/01_product_vision.md) • [Domain Glossary](docs/02_domain_glossary.md) • [PRD](docs/04_prd.md) |
| **2. Technical Architecture**| AOD, Tech Stack, ADRs, C4 Model | [Architecture](docs/05_architecture_overview.md) • [Tech Stack](docs/06_tech_stack.md) • [C4 Models](docs/09_c4_diagrams.md) |
| **3. Detailed Specifications**| SRS, Feature Specs, Event Catalog | [SRS](docs/11_srs.md) • [Feature Specs](docs/12_feature_specifications.md) • [Events](docs/14_event_catalog.md) |
| **4. Quality & DevOps** | Coding Standards, DI, CI/CD | [Standards](docs/16_coding_standards.md) • [Testing](docs/18_testing_strategy.md) • [CI/CD](docs/20_cicd_pipeline.md) |

---

## 🧪 Running Tests

```bash
# Run unit & integration tests
uv run pytest

# Check code format & linter
uv run ruff check .

# Check type hints
uv run mypy src
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
