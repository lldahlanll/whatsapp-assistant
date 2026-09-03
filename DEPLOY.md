# 🚀 Deploy Checklist — WhatsApp Assistant

## 1. Persiapan Sebelum Upload ke Server

- [ ] Pastikan semua file sensitif **TIDAK** ikut ter-upload:
  - `.env` — local dev secrets
  - `.env.docker` — Docker production secrets (**isi manual di server**)
  - `.venv/` — virtual environment (rebuild di Docker)
  - `__pycache__/`, `*.pyc` — Python bytecode

- [ ] File yang **perlu** ada di server:
  ```
  ├── src/
  ├── alembic/
  ├── alembic.ini
  ├── pyproject.toml
  ├── uv.lock
  ├── Dockerfile
  ├── docker-compose.yml
  ├── .dockerignore
  └── .env.example   ← template untuk membuat .env.docker
  ```

---

## 2. Transfer ke Server

### Opsi A — Git (Direkomendasikan)
```bash
# Di local — init dan push ke repo private
git init
git add .
git commit -m "feat: initial production release"
git remote add origin git@github.com:YOUR_ORG/whatsapp-assistant.git
git push -u origin main

# Di server
git clone git@github.com:YOUR_ORG/whatsapp-assistant.git
cd whatsapp-assistant
```

### Opsi B — rsync / SCP
```bash
rsync -avz --exclude='.venv' --exclude='.env' --exclude='.env.docker' \
  --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
  . user@server:/opt/whatsapp-assistant/
```

---

## 3. Setup di Server (Pertama Kali)

```bash
# Masuk ke direktori project
cd /opt/whatsapp-assistant

# Buat file secrets dari template
cp .env.example .env.docker

# Edit .env.docker — isi semua credentials
nano .env.docker
```

**Variabel wajib diisi di `.env.docker`:**
```env
APP_ENV="production"

# API Keys AI
GEMINI_API_KEYS=["YOUR_REAL_KEY"]
GROQ_API_KEYS=["YOUR_REAL_KEY"]
OPENROUTER_API_KEYS=["YOUR_REAL_KEY"]

# MySQL
MYSQL_HOST="your-db-host"
MYSQL_USER="your-user"
MYSQL_PASSWORD="your-password"
MYSQL_DB="your-database"
MYSQL_ROOT_PASSWORD="your-root-password"

# MikroTik (jika digunakan)
MIKROTIK_HOST="your-router-ip"
MIKROTIK_USERNAME="your-user"
MIKROTIK_PASSWORD="your-password"
```

---

## 4. Build & Deploy

```bash
# Build image dan jalankan container
docker-compose up -d --build

# Cek status container
docker-compose ps

# Lihat logs real-time
docker-compose logs -f app
```

---

## 5. Pairing WhatsApp

```bash
# Lihat QR Code untuk scan WhatsApp
docker-compose logs -f app
```

Scan QR Code menggunakan WhatsApp → Perangkat Tertaut → Tambah Perangkat.

---

## 6. Verifikasi

```bash
# Cek API berjalan (jika API_ENABLED=true)
curl http://localhost:8077/health

# Cek container tidak restart-loop
docker-compose ps
docker stats whatsapp-platform
```

---

## 7. Update Berikutnya

```bash
# Pull perubahan terbaru
git pull

# Rebuild dan restart
docker-compose up -d --build

# Jalankan migrasi DB (jika ada)
docker-compose exec app alembic upgrade head
```

---

## ⚠️ Keamanan — Wajib Diperhatikan

> **JANGAN PERNAH** commit file `.env` atau `.env.docker` ke Git.  
> Keduanya sudah masuk `.gitignore`.

- Gunakan password yang kuat untuk MySQL dan API Keys
- Set `API_KEY` di `.env.docker` untuk proteksi REST API
- Pertimbangkan firewall untuk membatasi akses port `8077` hanya dari IP tertentu
- Rotate API keys secara berkala
