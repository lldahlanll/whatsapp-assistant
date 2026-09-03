# 🧪 Enterprise Testing Strategy: Neonize Platform

> **Target Coverage:** Minimum **90%** (`--cov-fail-under=90`)  
> **Testing Stack:** `pytest` • `pytest-asyncio` • `httpx` • `pytest-cov` • `faker` • `factory-boy`  
> **Status:** Active Standard  
> **Version:** 2.0.0  
> **Last Updated:** 2026-08-03  

---

## 🎯 1. Overview & Coverage Target

Strategi pengujian pada proyek **Neonize Enterprise Platform** memadukan pendekatan **Testing Pyramid** dengan jaminan kualitas terotomatisasi. 

- **Target Coverage Minimum:** **90%** di seluruh lapisan aplikasi (`src/whatsapp_platform/`).
- **Domain Layer (`domain/`):** Target **100%** coverage (strict unit test).
- **Application Layer (`application/`):** Target **95%** coverage.
- **Infrastructure & Presentation (`infrastructure/`, `presentation/`):** Target **85%** coverage.

```bash
# Enforce minimum 90% coverage pada CI pipeline
uv run pytest --cov=whatsapp_platform --cov-report=term-missing --cov-fail-under=90
```

---

## 🧰 2. Standard Testing Tech Stack

| Library | Kegunaan | Contoh Implementasi |
| :--- | :--- | :--- |
| **`pytest`** | Test runner utama | Discovery, assertions, fixtures, dan test parameterization. |
| **`pytest-asyncio`** | Async test engine | Menguji coroutine `async/await` murni secara native. |
| **`httpx`** | HTTP Client | Menguji endpoint FastAPI (`AsyncClient`) dan webhook caller. |
| **`pytest-cov`** | Coverage report | Menghitung persentase baris kode yang teruji dan fail-fast jika < 90%. |
| **`faker`** | Fake data generator | Menghasilkan nama, nomor telepon WhatsApp (`628xxx`), dan teks acak. |
| **`factory-boy`** | Fixture factory | Generator objek domain dan model database terstruktur untuk testing. |

---

## 📑 3. Penjelasan 8 Tipe Pengujian (Test Types)

### 1️⃣ Unit Test
* **Definisi:** Pengujian terisolasi untuk menguji unit bisnis terkecil (fungsi, method, value object, entitas domain) secara 100% *in-memory* tanpa koneksi I/O (Database, Network, File System).
* **Fokus:** Domain logic, validasi JID, parsing command, pembuatan event.
* **Kecepatan:** Sangat cepat (< 1ms per test).

```python
# tests/unit/domain/test_jid.py
import pytest
from whatsapp_platform.domain.value_objects import JID
from whatsapp_platform.domain.exceptions import InvalidJIDException

def test_valid_whatsapp_jid_creation():
    raw_jid = "628123456789@s.whatsapp.net"
    jid = JID(raw_jid)
    assert jid.user == "628123456789"
    assert jid.server == "s.whatsapp.net"

def test_invalid_jid_raises_exception():
    with pytest.raises(InvalidJIDException):
        JID("invalid_jid_format")
```

---

### 2️⃣ Integration Test
* **Definisi:** Pengujian interaksi antar beberapa komponen/layer, seperti integrasi antara Use Case, Repository, dan Database asli (SQLite in-memory / test PostgreSQL).
* **Fokus:** Alur query ORM SQLAlchemy, Alembic migration, caching Redis, dan Event Bus pub/sub.

```python
# tests/integration/test_session_repository.py
import pytest
from whatsapp_platform.infrastructure.database.repositories import SQLAlchemySessionRepository
from whatsapp_platform.domain.entities import WhatsAppSession

@pytest.mark.asyncio
async def test_save_and_retrieve_session(async_session):
    repo = SQLAlchemySessionRepository(async_session)
    session_entity = WhatsAppSession(id="sess-100", phone_number="628123456789")

    await repo.save(session_entity)
    retrieved = await repo.get_by_id("sess-100")

    assert retrieved is not None
    assert retrieved.phone_number == "628123456789"
```

---

### 3️⃣ API Test (REST & Webhook)
* **Definisi:** Pengujian terhadap endpoint REST API (FastAPI) dan outgoing webhook menguji HTTP status code, request validation, response payload JSON, dan headers.
* **Tool:** `httpx.AsyncClient` (memanggil ASGI app tanpa membuka port jaringan).

```python
# tests/api/test_session_endpoints.py
import pytest
from httpx import AsyncClient, ASGITransport
from whatsapp_platform.presentation.api.main import app

@pytest.mark.asyncio
async def test_get_session_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/sessions/sess-100/status")
        
    assert response.status_code == 200
    assert response.json()["status"] == "CONNECTED"
```

---

### 4️⃣ Performance Test
* **Definisi:** Pengujian untuk mengukur *response latency*, memori footprint, dan konsumsi CPU saat aplikasi memproses pesan WhatsApp atau kueri AI.
* **Target:** Processing latency per pesan < 100ms (non-AI) dan memory leak 0 bytes.

---

### 5️⃣ Load Test
* **Definisi:** Pengujian untuk mensimulasikan beban kerja normal hingga beban puncak (*peak load*) yang diperkirakan di lingkungan produksi (misal: 5,000 pesan masuk per menit).
* **Tool:** `Locust` atau `k6`.
* **Fokus:** Mengukur *throughput* (RPS / Messages Per Second) dan kestabilan antrean worker Redis ARQ.

---

### 6️⃣ Stress Test
* **Definisi:** Pengujian dengan mendorong beban aplikasi **melewati batas kapasitas maksimal** untuk menemukan *breaking point*, menguji ketahanan sistem dari crash, dan memverifikasi fitur auto-recovery.
* **Fokus:** Menguji perilaku bot saat jaringan terputus tiba-tiba atau saat Redis RAM 100% penuh.

---

### 7️⃣ Regression Test
* **Definisi:** Suite pengujian otomatis yang dijalankan pada pipeline CI/CD setiap kali ada commit / Pull Request baru untuk memastikan perubahan kode baru tidak merusak fitur lama yang sudah stabil.
* **Pelaksanaan:** Otomatis via GitHub Actions pada setiap PR.

---

### 8️⃣ End-to-End (E2E) Test
* **Definisi:** Pengujian alur lengkap dari awal hingga akhir (*end-to-end flow*) yang mensimulasikan kejadian dunia nyata: Menerima event pesan dari Neonize → Parsing Command → Memanggil LLM AI → Menyimpan DB → Mengirim balasan WhatsApp.
* **Tool:** Mock Neonize Gateway & Automated Staged Fixtures.

---

## 🏭 4. Factory & Fake Data Setup (Factory-Boy & Faker)

Penggunaan `factory-boy` dan `faker` untuk membuat data dummy yang konsisten dan type-safe di seluruh unit & integration test.

```python
# tests/fixtures/factories.py
import factory
from faker import Faker
from whatsapp_platform.domain.entities import WhatsAppSession, Message

fake = Faker("id_ID")  # Locale Indonesia

class WhatsAppSessionFactory(factory.Factory):
    class Meta:
        model = WhatsAppSession

    id = factory.Sequence(lambda n: f"session-{n}")
    phone_number = factory.LazyFunction(lambda: f"628{fake.msisdn()[3:]}")
    is_connected = True

class MessageFactory(factory.Factory):
    class Meta:
        model = Message

    id = factory.LazyFunction(lambda: f"MSG-{fake.uuid4()[:8]}")
    sender_jid = factory.LazyFunction(lambda: f"628{fake.msisdn()[3:]}@s.whatsapp.net")
    body = factory.LazyFunction(fake.sentence)
```

---

## 🏃 5. Cara Menjalankan Suite Test

```bash
# 1. Jalankan seluruh Unit Tests
uv run pytest tests/unit

# 2. Jalankan Integration Tests
uv run pytest tests/integration

# 3. Jalankan API Tests
uv run pytest tests/api

# 4. Jalankan Coverage Check (WAJIB > 90%)
uv run pytest --cov=src/whatsapp_platform --cov-report=term-missing --cov-fail-under=90

# 5. Generate HTML Coverage Report
uv run pytest --cov=src/whatsapp_platform --cov-report=html
```
