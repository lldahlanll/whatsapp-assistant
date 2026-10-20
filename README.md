# 🤖 WhatsApp Assistant Platform

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Neonize](https://img.shields.io/badge/whatsapp-Neonize-green.svg)](https://github.com/krypton-byte/neonize)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Architecture: Clean](https://img.shields.io/badge/architecture-Clean%20%2B%20DDD-orange.svg)](docs/05_architecture_overview.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Platform **WhatsApp Assistant** production-grade berbasis **Python 3.12+** dan **Neonize**. Dilengkapi **AI Assistant multi-provider**, **manajemen keuangan pribadi**, **monitoring jaringan MikroTik**, **customer lookup**, dan **REST API** — semuanya dibangun dengan prinsip **Clean Architecture** & **DDD**.

---

## ✨ Fitur Utama

### 🤖 AI Assistant (Multi-Provider)
- Balasan otomatis menggunakan AI di private chat & group (mention)
- **4 provider** didukung: **Gemini**, **Groq**, **OpenRouter**, **9router** (self-hosted)
- Automatic failover & key rotation antar provider
- Rate limiting per-chat untuk mencegah abuse
- Konteks percakapan multi-turn dengan history
- Intent routing otomatis: chat, finance, network, vision
- Support **image/vision analysis** (kirim gambar + pertanyaan)
- Per-chat model override & konfigurasi

### 💰 Manajemen Keuangan Pribadi
- Catat pemasukan, pengeluaran, dan transfer antar rekening
- Kelola multi-rekening (bank, e-wallet, kas, tabungan, deposito, investasi)
- Budget/anggaran per kategori dengan tracking progress
- Laporan bulanan & ringkasan pengeluaran per kategori
- Riwayat transaksi dengan filter (tanggal, akun, kategori, tipe)
- Edit & hapus transaksi
- **Natural language** — cukup ngobrol dengan AI untuk catat keuangan
- **Command shortcut** — `!finance` untuk akses cepat

### 🌐 Monitoring Jaringan MikroTik
- Monitoring kesehatan router (CPU, memory, uptime, disk)
- Analisis traffic real-time per interface
- Audit keamanan: user, service, firewall
- Laporan DHCP leases & client terhubung
- Monitoring firewall rules
- Log system router
- Permission-based access control per JID
- Caching otomatis untuk mengurangi load router
- **Natural language** — tanya AI tentang kondisi jaringan
- **Command shortcut** — `!network` untuk monitoring cepat

### 👥 Manajemen Group WhatsApp
- Info group (members, admins, deskripsi)
- Kick, add, promote, demote anggota
- Set nama group
- Generate invite link
- Semua via perintah `!group`, `!kick`, `!add`, `!promote`, `!demote`, `!setname`, `!invitelink`

### 🔍 Customer Lookup
- Lookup data pelanggan dari database MySQL eksternal
- Deteksi otomatis nomor telepon dalam pesan
- Whitelist group yang diizinkan
- Rate limiting per pengirim

### 🌐 REST API (FastAPI)
- `GET /health` — Health check
- `POST /api/messages/send` — Kirim pesan teks
- `GET /api/session/status` — Status sesi WhatsApp
- `GET /api/groups` — Daftar group
- Otentikasi via `X-API-Key` header
- Auto-generated OpenAPI/Swagger docs di `/docs`

### 📄 Media Processing
- **OCR** — Ekstrak teks dari gambar (Pillow)
- **PDF Text Extractor** — Ekstrak teks dari dokumen PDF (PyMuPDF)
- **Audio Transcription** — Pipeline fallback untuk transkripsi audio

### ⚙️ Infrastruktur & DevOps
- **Async-first** — Full `asyncio` untuk performa optimal
- **SQLAlchemy 2.0 Async** + **Alembic** auto-migration
- **Structured logging** dengan `structlog`
- **Docker & Docker Compose** siap deploy
- **Graceful shutdown** dengan signal handling (SIGINT/SIGTERM)
- **Dependency Injection** container untuk testabilitas tinggi

---

## 🏗️ Arsitektur

```
┌──────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                         │
│           (FastAPI REST API, CLI, Event Handlers)                │
├──────────────────────────────────────────────────────────────────┤
│                      FEATURE MODULES (Vertical Slices)          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ Session  │ │Messaging │ │ Commands │ │   AI Assistant    │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  ┌──────────┐ ┌──────────────┐ ┌────────────────────────────┐  │
│  │ Finance  │ │Customer Lookup│ │  Network (MikroTik)       │  │
│  └──────────┘ └──────────────┘ └────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                      APPLICATION LAYER                          │
│       (Use Cases, Event Bus, Feature Registry, AI Reply)        │
├──────────────────────────────────────────────────────────────────┤
│                        DOMAIN LAYER                             │
│   (Entities, Value Objects, Domain Events, Repository Contracts)│
├──────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE LAYER                        │
│  (Neonize Gateway, SQLAlchemy Repos, AI Providers, MikroTik,   │
│   MySQL Client, Config, Structured Logging)                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start

### Prerequisites
- Python >= 3.12
- [uv](https://github.com/astral-sh/uv) package manager
- Docker & Docker Compose (opsional, untuk deployment)

### 1. Clone & Install

```bash
git clone https://github.com/your-org/whatsapp-assistant.git
cd whatsapp-assistant
uv sync
```

### 2. Konfigurasi Environment

```bash
cp .env.example .env
# Edit .env — isi konfigurasi yang diperlukan
```

Konfigurasi minimal:
```env
# Session
SESSION_NAME="my_session"
PAIRING_METHOD="qr"

# AI (minimal 1 provider)
GEMINI_API_KEYS="your-api-key"
# atau
GROQ_API_KEYS="your-api-key"
# atau
OPENROUTER_API_KEYS="your-api-key"
```

> 📖 Lihat [docs/CONFIGURATION.md](docs/CONFIGURATION.md) untuk penjelasan lengkap semua variabel environment.

### 3. Jalankan Aplikasi

```bash
uv run python -m whatsapp_platform
```

Scan **QR Code** yang muncul di terminal menggunakan WhatsApp → **Perangkat Tertaut** → **Tambah Perangkat**.

### 4. Tes Koneksi

Kirim pesan ke nomor WhatsApp yang terhubung:
```
!ping
```
Bot akan membalas `🏓 Pong!` jika berhasil.

---

## 📖 Daftar Perintah (Commands)

Semua perintah diawali dengan prefix `!` (bisa dikustomisasi via `COMMAND_PREFIX`).

### Umum

| Perintah | Deskripsi |
|---|---|
| `!ping` | Cek apakah bot aktif |
| `!help` | Tampilkan daftar semua perintah |
| `!status` | Info sistem: uptime, memory, Python version, OS |

### AI Assistant

| Perintah | Deskripsi |
|---|---|
| `!ai on` | Aktifkan AI auto-reply di chat ini |
| `!ai off` | Nonaktifkan AI auto-reply |
| `!ai status` | Cek status AI & model yang digunakan |
| `!ai reset` | Reset konteks percakapan AI |
| `!ai model <nama>` | Ganti model AI per-chat |
| `!ai stats` | Statistik penggunaan LLM (daily counters, key pool) |

### Keuangan (`!finance`)

| Perintah | Contoh | Deskripsi |
|---|---|---|
| `!finance masuk` | `!finance masuk 5jt gaji` | Catat pemasukan |
| `!finance keluar` | `!finance keluar 50rb makan siang` | Catat pengeluaran |
| `!finance transfer` | `!finance transfer 100rb BCA BRI` | Transfer antar rekening |
| `!finance saldo` | `!finance saldo` | Lihat semua saldo |
| `!finance riwayat` | `!finance riwayat 10` | Riwayat transaksi terakhir |
| `!finance laporan` | `!finance laporan 10` | Laporan bulanan (bulan ke-10) |
| `!finance rekening` | `!finance rekening` | Daftar rekening |
| `!finance rekening baru` | `!finance rekening baru GoPay ewallet 200rb` | Buat rekening baru |
| `!finance rekening hapus` | `!finance rekening hapus BCA` | Hapus rekening |
| `!finance budget` | `!finance budget makan 1jt` | Atur budget kategori |
| `!finance reset` | `!finance reset` | Preview/reset semua data |

> 💡 **Atau cukup ngobrol natural** (jika AI aktif): _"catat pengeluaran 50rb buat makan siang"_, _"berapa saldo aku?"_, _"laporan keuangan bulan ini"_

### Jaringan MikroTik (`!network` / `!net`)

| Perintah | Deskripsi |
|---|---|
| `!network health` | Kesehatan router: CPU, RAM, uptime, disk |
| `!network traffic` | Traffic per interface |
| `!network security` | Audit user, service, firewall |
| `!network dhcp` | Daftar DHCP leases & client |
| `!network firewall` | Firewall rules summary |
| `!network logs` | System log router |

> 💡 **Atau tanya AI secara natural**: _"gimana kondisi router sekarang?"_, _"ada berapa client yang konek?"_

### Manajemen Group

| Perintah | Deskripsi |
|---|---|
| `!group` | Info group (member, admin, deskripsi) |
| `!kick @user` | Keluarkan anggota dari group |
| `!add 628xxx` | Tambahkan anggota ke group |
| `!promote @user` | Jadikan anggota sebagai admin |
| `!demote @user` | Cabut status admin |
| `!setname Nama Baru` | Ubah nama group |
| `!invitelink` | Generate link undangan group |

---

## 🐳 Deploy dengan Docker

```bash
# 1. Salin dan isi konfigurasi production
cp .env.example .env.docker
nano .env.docker

# 2. Build & jalankan
docker-compose up -d --build

# 3. Lihat QR code untuk pairing
docker-compose logs -f app

# 4. Verifikasi
curl http://localhost:8077/health
```

> 📖 Lihat [DEPLOY.md](DEPLOY.md) untuk panduan deployment lengkap.

---

## 🧪 Testing

```bash
# Jalankan semua test
uv run pytest

# Dengan coverage
uv run pytest --cov=whatsapp_platform

# Linting & formatting
uv run ruff check .

# Type checking
uv run mypy src
```

---

## 📂 Struktur Proyek

```
whatsapp-assistant/
├── src/whatsapp_platform/
│   ├── domain/                # Entities, Value Objects, Events, Contracts
│   ├── application/           # Use Cases, Event Bus, Feature Registry
│   ├── features/
│   │   ├── session/           # WhatsApp session lifecycle
│   │   ├── messaging/         # Auto-persist messages & conversations
│   │   ├── commands/          # Command router & handlers
│   │   ├── ai/                # AI auto-reply handler & config
│   │   ├── finance/           # Personal finance service
│   │   ├── customer_lookup/   # External MySQL customer lookup
│   │   └── network/           # MikroTik network monitoring
│   ├── infrastructure/
│   │   ├── ai/                # AI providers (Gemini, Groq, OpenRouter, 9router)
│   │   ├── neonize/           # WhatsApp gateway adapter
│   │   ├── database/          # SQLAlchemy repos & Alembic migrations
│   │   ├── mikrotik/          # MikroTik REST API client
│   │   ├── customer_lookup/   # MySQL repository
│   │   ├── finance/           # Finance tool schemas & executor
│   │   ├── config/            # Pydantic Settings
│   │   └── logging/           # Structured logging
│   ├── presentation/
│   │   ├── api/               # FastAPI REST endpoints
│   │   ├── cli/               # CLI interface
│   │   └── events/            # Domain event presenters
│   ├── container.py           # DI Container wiring
│   └── app.py                 # Application lifecycle runner
├── docs/                      # 28+ dokumen teknis
├── tests/                     # Unit & integration tests
├── alembic/                   # Database migrations
├── docker-compose.yml
├── Dockerfile
├── DEPLOY.md                  # Panduan deployment
├── CONTRIBUTING.md            # Panduan kontribusi
├── CHANGELOG.md               # Catatan perubahan
└── pyproject.toml
```

---

## 📚 Dokumentasi Lengkap

| Kategori | Dokumen |
|---|---|
| **Visi & Produk** | [Product Vision](docs/01_product_vision.md) · [Domain Glossary](docs/02_domain_glossary.md) · [PRD](docs/04_prd.md) |
| **Arsitektur** | [Architecture Overview](docs/05_architecture_overview.md) · [Tech Stack](docs/06_tech_stack.md) · [C4 Diagrams](docs/09_c4_diagrams.md) |
| **Spesifikasi** | [SRS](docs/11_srs.md) · [Feature Specs](docs/12_feature_specifications.md) · [Event Catalog](docs/14_event_catalog.md) |
| **Konfigurasi** | [Configuration Guide](docs/CONFIGURATION.md) |
| **Quality** | [Coding Standards](docs/18_coding_standards.md) · [Testing Strategy](docs/18_testing_strategy.md) |
| **Deployment** | [Deploy Checklist](DEPLOY.md) · [CI/CD Pipeline](docs/20_cicd_pipeline.md) |
| **Kontribusi** | [Contributing Guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) |

---

## 🛡️ Keamanan

- API key disimpan di `.env` (tidak di-commit ke git)
- REST API dilindungi `X-API-Key` authentication
- Network commands menggunakan JID whitelist
- Customer lookup dibatasi per group
- AI rate limiting per-chat untuk mencegah abuse
- Per-chat privacy notice saat AI diaktifkan

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
