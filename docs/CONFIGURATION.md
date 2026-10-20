# ⚙️ Configuration Guide — WhatsApp Assistant Platform

Panduan lengkap semua variabel environment yang tersedia untuk mengkonfigurasi WhatsApp Assistant Platform.

Semua konfigurasi dilakukan melalui file `.env` (local development) atau `.env.docker` (production). Salin dari template:

```bash
cp .env.example .env
```

---

## 📋 Daftar Lengkap Environment Variables

### 🔧 Aplikasi Umum

| Variable | Default | Deskripsi |
|---|---|---|
| `APP_NAME` | `whatsapp-platform` | Nama aplikasi (untuk logging) |
| `APP_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DEBUG` | `true` | Aktifkan debug logging |
| `LOG_LEVEL` | `INFO` | Level log: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `COMMAND_PREFIX` | `!` | Prefix perintah bot (contoh: `!ping`) |

---

### 📱 WhatsApp Session

| Variable | Default | Deskripsi |
|---|---|---|
| `SESSION_NAME` | `default_session` | Nama identifikasi sesi WhatsApp |
| `PAIRING_METHOD` | `qr` | Metode pairing: `qr` (scan QR) atau `code` (pairing code) |
| `PAIRING_PHONE_NUMBER` | _(kosong)_ | Nomor telepon untuk pairing code, format: `628xxxxxxxxxx` |

**Catatan:**
- Gunakan `PAIRING_METHOD=qr` untuk scan QR Code di terminal
- Gunakan `PAIRING_METHOD=code` jika QR tidak bisa ditampilkan (e.g. headless server), isi `PAIRING_PHONE_NUMBER`

---

### 💾 Database

| Variable | Default | Deskripsi |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./storage/session.db` | Connection string database utama (SQLAlchemy format) |

Database SQLite akan otomatis dibuat dan di-migrasi saat startup menggunakan Alembic.

---

### 🌐 REST API (FastAPI)

| Variable | Default | Deskripsi |
|---|---|---|
| `API_ENABLED` | `true` | Aktifkan REST API server |
| `API_HOST` | `0.0.0.0` | Host bind API server |
| `API_PORT` | `8077` | Port API server |
| `API_KEY` | _(kosong)_ | Secret key untuk autentikasi `X-API-Key`. Kosong = API tidak dilindungi |

**Endpoints yang tersedia** (jika `API_ENABLED=true`):

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger/OpenAPI documentation |
| `POST` | `/api/messages/send` | Kirim pesan teks |
| `GET` | `/api/session/status` | Status sesi WhatsApp |
| `GET` | `/api/groups` | Daftar group |

**Contoh request dengan API key:**
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8077/api/session/status
```

---

### 🤖 AI Multi-Provider

Platform mendukung 4 provider AI dengan automatic failover. Cukup isi **minimal 1 provider** untuk mengaktifkan fitur AI.

| Variable | Default | Deskripsi |
|---|---|---|
| `GEMINI_API_KEYS` | _(kosong)_ | API key Gemini (comma-separated untuk multiple keys) |
| `GROQ_API_KEYS` | _(kosong)_ | API key Groq (comma-separated) |
| `OPENROUTER_API_KEYS` | _(kosong)_ | API key OpenRouter (comma-separated) |

**Contoh multiple keys** (untuk key rotation saat rate limit):
```env
GEMINI_API_KEYS="AIzaSy1xxxxx,AIzaSy2xxxxx,AIzaSy3xxxxx"
GROQ_API_KEYS="gsk_1xxxxx,gsk_2xxxxx"
```

#### 9router (Self-Hosted LLM Router)

Untuk pengguna yang menjalankan LLM router sendiri (OpenAI-compatible):

| Variable | Default | Deskripsi |
|---|---|---|
| `NINEROUTER_API_KEYS` | _(kosong)_ | API key 9router (comma-separated) |
| `NINEROUTER_BASE_URL` | _(kosong)_ | Base URL, contoh: `http://192.168.1.100:4000/v1` |
| `NINEROUTER_MODEL_CHAT` | `chat-pool` | Virtual model name untuk chat intent |
| `NINEROUTER_MODEL_TOOLS` | `tools-pool` | Virtual model name untuk tool calling (finance/network) |
| `NINEROUTER_MODEL_VISION` | `vision-pool` | Virtual model name untuk vision/image analysis |

---

### 🧠 AI Behaviour & Tuning

| Variable | Default | Deskripsi |
|---|---|---|
| `AI_COOLDOWN_DEFAULT_SECONDS` | `60.0` | Default cooldown saat API key kena rate limit |
| `AI_RATE_LIMIT_MAX_REQUESTS` | `5` | Max request AI per menit per chat |
| `AI_RATE_LIMIT_WINDOW_SECONDS` | `60.0` | Window rate limiting per chat (detik) |
| `AI_CONTEXT_WINDOW_MESSAGES` | `20` | Max pesan dalam konteks LLM |
| `AI_MAX_CONTEXT_CHARS` | `16000` | Max karakter konteks yang dikirim ke LLM |
| `AI_BOT_MENTION_NAME` | _(kosong)_ | Nama bot untuk deteksi @mention di group chat |
| `AI_HTTP_TIMEOUT_SECONDS` | `30.0` | Timeout HTTP request ke AI provider |
| `AI_VISION_ENABLED` | `true` | Analisis gambar: pesan gambar (opsional caption) yang memicu AI dikirim ke model vision (`NINEROUTER_MODEL_VISION`) |
| `AI_IMAGE_MAX_BYTES` | `5242880` | Ukuran maksimum gambar (byte, default 5 MB); gambar lebih besar ditolak dengan pesan ke user |

**Pengaturan history per-intent:**

| Variable | Default | Deskripsi |
|---|---|---|
| `AI_CHAT_HISTORY_LIMIT` | `3` | Jumlah pesan history untuk chat biasa |
| `AI_FINANCE_HISTORY_LIMIT` | `5` | Jumlah pesan history untuk intent finance |
| `AI_NETWORK_HISTORY_LIMIT` | `3` | Jumlah pesan history untuk intent network |
| `AI_COMPLEX_HISTORY_LIMIT` | `8` | Jumlah pesan history untuk intent complex |

**Pengaturan tool calling:**

| Variable | Default | Deskripsi |
|---|---|---|
| `AI_MAX_TOOL_RESULT_CHARS` | `1000` | Max karakter hasil tool call yang dikirim ke LLM |
| `AI_MAX_TOOL_ITERATIONS` | `3` | Max iterasi agentic loop (tool → LLM → tool) |

---

### 🔍 Customer Lookup (MySQL)

Untuk lookup data pelanggan dari database MySQL eksternal.

| Variable | Default | Deskripsi |
|---|---|---|
| `MYSQL_HOST` | _(kosong)_ | MySQL host. Kosong = fitur dinonaktifkan |
| `MYSQL_PORT` | `3306` | MySQL port |
| `MYSQL_USER` | _(kosong)_ | MySQL username |
| `MYSQL_PASSWORD` | _(kosong)_ | MySQL password |
| `MYSQL_DB` | _(kosong)_ | MySQL database name |
| `MYSQL_POOL_MIN_SIZE` | `1` | Minimum pool size |
| `MYSQL_POOL_MAX_SIZE` | `3` | Maximum pool size |
| `MYSQL_QUERY_TIMEOUT_MS` | `3000` | Query timeout (milidetik) |
| `CUSTOMER_LOOKUP_ALLOWED_GROUPS` | _(kosong)_ | Group JID yang diizinkan (comma-separated). Kosong = semua group diizinkan |

---

### 🌐 MikroTik Network Monitoring

Integrasi dengan router MikroTik via REST API.

| Variable | Default | Deskripsi |
|---|---|---|
| `MIKROTIK_ENABLED` | `false` | Aktifkan integrasi MikroTik |
| `MIKROTIK_HOST` | _(kosong)_ | IP atau hostname router MikroTik |
| `MIKROTIK_PORT` | `80` | Port REST API (80 HTTP / 443 HTTPS) |
| `MIKROTIK_USERNAME` | _(kosong)_ | Username MikroTik |
| `MIKROTIK_PASSWORD` | _(kosong)_ | Password MikroTik |
| `MIKROTIK_USE_SSL` | `false` | Gunakan HTTPS |
| `MIKROTIK_VERIFY_SSL` | `false` | Verifikasi sertifikat SSL |
| `MIKROTIK_TIMEOUT` | `5.0` | Timeout per request (detik) |

**Keamanan & Access Control:**

| Variable | Default | Deskripsi |
|---|---|---|
| `NETWORK_ALLOWED_JIDS` | _(kosong)_ | Whitelist JID yang boleh menjalankan perintah network (comma-separated). Kosong = semua boleh |

**Cache TTL (seconds):**

| Variable | Default | Deskripsi |
|---|---|---|
| `NETWORK_CACHE_TTL_SYSTEM` | `30` | Cache kesehatan sistem |
| `NETWORK_CACHE_TTL_FIREWALL` | `60` | Cache firewall rules |
| `NETWORK_CACHE_TTL_ROUTES` | `30` | Cache routes |
| `NETWORK_CACHE_TTL_DHCP` | `15` | Cache DHCP leases |

---

## 📝 Contoh Konfigurasi Lengkap

### Development (Minimal)

```env
APP_ENV="development"
DEBUG=true
SESSION_NAME="dev_session"
PAIRING_METHOD="qr"
GEMINI_API_KEYS="your-gemini-key"
```

### Production (Full Feature)

```env
APP_NAME="whatsapp-assistant"
APP_ENV="production"
DEBUG=false
LOG_LEVEL="INFO"

# Session
SESSION_NAME="prod_session"
PAIRING_METHOD="qr"

# Database
DATABASE_URL="sqlite+aiosqlite:///./storage/session.db"

# REST API
API_ENABLED=true
API_HOST="0.0.0.0"
API_PORT=8077
API_KEY="your-strong-secret-api-key"

# AI Providers (multiple keys for rotation)
GEMINI_API_KEYS="key1,key2,key3"
GROQ_API_KEYS="key1,key2"
OPENROUTER_API_KEYS="key1"

# AI Behaviour
AI_RATE_LIMIT_MAX_REQUESTS=5
AI_RATE_LIMIT_WINDOW_SECONDS=60
AI_BOT_MENTION_NAME="Nara"
AI_HTTP_TIMEOUT_SECONDS=30

# Customer Lookup MySQL
MYSQL_HOST="127.0.0.1"
MYSQL_PORT=3306
MYSQL_USER="wa_user"
MYSQL_PASSWORD="your-mysql-password"
MYSQL_DB="customer_db"
CUSTOMER_LOOKUP_ALLOWED_GROUPS="12036301234567890@g.us"

# MikroTik
MIKROTIK_ENABLED=true
MIKROTIK_HOST="192.168.88.1"
MIKROTIK_PORT=80
MIKROTIK_USERNAME="ai-readonly"
MIKROTIK_PASSWORD="your-router-password"
NETWORK_ALLOWED_JIDS="628123456789@s.whatsapp.net"

# Command
COMMAND_PREFIX="!"
```

---

## ⚠️ Tips Keamanan

1. **Jangan pernah** commit file `.env` atau `.env.docker` ke Git
2. Gunakan **password yang kuat** untuk MySQL dan API keys
3. Set `API_KEY` untuk proteksi REST API
4. Gunakan `NETWORK_ALLOWED_JIDS` untuk membatasi akses network commands
5. Buat user **read-only** di MikroTik untuk integrasi bot
6. Rotate API keys secara berkala
7. Pertimbangkan firewall untuk membatasi akses port API
