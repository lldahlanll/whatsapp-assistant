# DOC-004 · Product Requirements Document (PRD)

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Product Architect  

---

## 1. Executive Summary

Platform WhatsApp berbasis Python + Neonize yang didesain sebagai **fondasi production-grade** untuk membangun intelligent messaging automation. Platform ini bukan sekadar bot, melainkan sebuah ekosistem yang dapat dikembangkan selama bertahun-tahun tanpa perlu rewrite dari awal.

**Target utama:** Developer Python yang ingin membangun solusi WhatsApp serius tanpa mengorbankan kualitas kode.

---

## 2. Problem Statement

Ekosistem bot WhatsApp Python saat ini memiliki gap besar antara "library sederhana untuk hello world" dan "platform siap production". Developer yang ingin membangun solusi serious terpaksa harus:

1. Membangun arsitektur dari nol (memakan waktu berminggu-minggu)
2. Menanggung hutang teknis sejak awal karena tidak ada blueprint
3. Sulit mendapatkan kolaborasi tim karena tidak ada standar kode
4. Rentan terhadap breaking changes library karena tidak ada abstraction layer

Platform ini mengisi gap tersebut.

---

## 3. Functional Requirements

### 3.1 Session Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | Platform HARUS dapat memulai session baru via QR code scan | Must Have |
| FR-002 | Platform HARUS menyimpan session credentials secara persistent | Must Have |
| FR-003 | Platform HARUS melakukan reconnect otomatis ketika koneksi terputus | Must Have |
| FR-004 | Platform HARUS mendukung graceful shutdown (disconnect tanpa logout) | Must Have |
| FR-005 | Platform HARUS melaporkan perubahan status session via domain event | Must Have |
| FR-006 | Platform HARUS mengimplementasikan exponential backoff saat reconnect | Should Have |
| FR-007 | Platform HARUS mendukung QR code display ulang jika QR expired | Should Have |

### 3.2 Messaging — Inbound

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-010 | Platform HARUS dapat menerima pesan teks dari personal chat | Must Have |
| FR-011 | Platform HARUS dapat menerima pesan teks dari group chat | Must Have |
| FR-012 | Platform HARUS dapat menerima pesan berisi gambar | Must Have |
| FR-013 | Platform HARUS dapat menerima pesan berisi video | Should Have |
| FR-014 | Platform HARUS dapat menerima pesan berisi dokumen | Should Have |
| FR-015 | Platform HARUS dapat menerima pesan berisi audio | Should Have |
| FR-016 | Platform HARUS dapat menerima pesan yang merupakan reply | Should Have |
| FR-017 | Platform HARUS dapat menerima pesan poll | Could Have |
| FR-018 | Setiap pesan masuk HARUS di-map ke `IncomingMessage` domain object | Must Have |

### 3.3 Messaging — Outbound

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-020 | Platform HARUS dapat mengirim pesan teks ke personal chat | Must Have |
| FR-021 | Platform HARUS dapat mengirim pesan teks ke group chat | Must Have |
| FR-022 | Platform HARUS dapat mengirim pesan berisi gambar | Must Have |
| FR-023 | Platform HARUS dapat mengirim pesan berisi dokumen | Should Have |
| FR-024 | Platform HARUS dapat mengirim pesan berisi audio | Should Have |
| FR-025 | Platform HARUS dapat mengirim reply ke pesan tertentu | Should Have |
| FR-026 | Platform HARUS dapat mengirim pesan dengan tombol/interaktif | Could Have |

### 3.4 Command Routing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-030 | Platform HARUS mendukung prefix-based command parsing | Must Have |
| FR-031 | Platform HARUS mendukung regex-based command matching | Should Have |
| FR-032 | Platform HARUS mendukung registrasi handler per command name | Must Have |
| FR-033 | Platform HARUS mendukung middleware chain untuk command | Should Have |
| FR-034 | Platform HARUS mengirim pesan "command tidak dikenal" jika tidak ada handler | Should Have |
| FR-035 | Platform HARUS mendukung help command yang auto-generate dari registered commands | Could Have |

### 3.5 Feature Module System

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-040 | Platform HARUS mendukung penambahan feature module tanpa edit core code | Must Have |
| FR-041 | Setiap feature module HARUS dapat mendaftarkan event handlers-nya | Must Have |
| FR-042 | Setiap feature module HARUS dapat mendaftarkan command handlers-nya | Must Have |
| FR-043 | Feature modules HARUS dapat di-enable/disable via konfigurasi | Should Have |
| FR-044 | Platform HARUS mendukung hot-reload feature module (tanpa restart penuh) | Could Have |

### 3.6 Configuration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-050 | Semua konfigurasi HARUS dapat diatur via environment variables | Must Have |
| FR-051 | Platform HARUS mendukung file `.env` untuk development | Must Have |
| FR-052 | Konfigurasi HARUS divalidasi saat startup (fail fast) | Must Have |
| FR-053 | Platform HARUS mendukung konfigurasi berbeda per environment (dev/staging/prod) | Should Have |
| FR-054 | Secret values HARUS tidak pernah di-log | Must Have |

### 3.7 Logging & Observability

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-060 | Platform HARUS menghasilkan structured logs dalam format JSON | Must Have |
| FR-061 | Setiap log entry HARUS mengandung: timestamp, level, correlation_id, message, context | Must Have |
| FR-062 | Platform HARUS mendukung log level yang dapat dikonfigurasi | Must Have |
| FR-063 | Platform HARUS menyediakan health check status | Should Have |
| FR-064 | Platform HARUS mengekspos basic metrics (message count, error rate) | Could Have |

### 3.8 AI Integration (Future Feature)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-070 | Platform HARUS memiliki interface `IAIProvider` yang LLM-agnostic | Should Have |
| FR-071 | Platform HARUS mendukung context passing ke LLM (conversation history) | Should Have |
| FR-072 | Platform HARUS mendukung implementasi OpenAI, Gemini, dan local model | Could Have |

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR-001 | Waktu pemrosesan pesan masuk | p95 < 500ms (tanpa AI call) |
| NFR-002 | Waktu reconnect setelah disconnect | < 30 detik (dengan session tersimpan) |
| NFR-003 | Memory footprint platform (baseline) | < 256MB |
| NFR-004 | Throughput pesan yang bisa diproses | > 100 pesan/menit |

### 4.2 Reliability

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR-010 | Uptime platform | >= 99.5% per bulan |
| NFR-011 | Session recovery rate (tanpa re-scan QR) | >= 95% setelah disconnect |
| NFR-012 | Pesan tidak boleh hilang (at-least-once delivery) | 100% |
| NFR-013 | Platform harus dapat restart tanpa kehilangan state kritis | Must |

### 4.3 Security

| ID | Requirement |
|----|-------------|
| NFR-020 | Session credentials TIDAK BOLEH disimpan dalam plaintext di kode |
| NFR-021 | API keys dan secrets HARUS diambil dari environment variables |
| NFR-022 | Log TIDAK BOLEH mengandung credential atau isi pesan user (configurable) |
| NFR-023 | Dependency HARUS di-scan untuk known vulnerabilities di CI |

### 4.4 Maintainability

| ID | Requirement |
|----|-------------|
| NFR-030 | Test coverage HARUS >= 80% |
| NFR-031 | Mypy strict mode HARUS pass 100% |
| NFR-032 | Ruff linter HARUS pass tanpa error |
| NFR-033 | Cyclomatic complexity per fungsi HARUS <= 10 |
| NFR-034 | Setiap public class dan function HARUS memiliki docstring |

### 4.5 Scalability

| ID | Requirement |
|----|-------------|
| NFR-040 | Arsitektur HARUS mendukung penambahan fitur tanpa perlu refactor core |
| NFR-041 | Processing heavy tasks HARUS melalui task queue (tidak blocking event loop) |
| NFR-042 | Platform HARUS stateless kecuali session storage (untuk scaling horizontal) |

---

## 5. MVP Scope vs Future Scope

### MVP (v0.1.0 — v0.9.0)
Fitur-fitur yang harus ada sebelum disebut "production-ready":

- [x] Session management (QR, save, reconnect)
- [x] Receive/send text messages
- [x] Receive/send media (image, document)
- [x] Command routing (prefix-based)
- [x] Feature module system (minimal)
- [x] Structured logging
- [x] Docker + Docker Compose
- [x] Unit tests >= 80% coverage
- [x] Type hints + Mypy strict
- [x] Configuration via env vars

### v1.0.0 (Stable)
- [ ] Full media support (video, audio, sticker)
- [ ] Middleware chain
- [ ] AI integration layer
- [ ] REST API layer
- [ ] Scheduler & broadcast
- [ ] Comprehensive integration tests

### v2.0.0 (Advanced)
- [ ] Multi-session management
- [ ] Web admin dashboard
- [ ] Plugin marketplace
- [ ] Advanced analytics

---

## 6. Acceptance Criteria

### AC-001 (untuk FR-001, FR-002, FR-003)
```
GIVEN platform baru tanpa session tersimpan
WHEN developer menjalankan platform
THEN QR code ditampilkan di terminal dalam < 5 detik

GIVEN QR code sudah di-scan
WHEN autentikasi berhasil
THEN session disimpan ke storage dan platform menampilkan "Connected"

GIVEN platform berjalan dan koneksi internet terputus
WHEN koneksi internet kembali
THEN platform reconnect otomatis dalam < 30 detik tanpa re-scan QR
```

### AC-002 (untuk FR-010, FR-018)
```
GIVEN platform berjalan (session = CONNECTED)
WHEN user mengirim pesan "Hello" ke nomor yang terhubung
THEN dalam < 500ms:
  - MessageReceived event dipublish
  - IncomingMessage object tersedia dengan body="Hello"
  - Log entry ter-generate dengan correlation_id
```

### AC-003 (untuk FR-030, FR-032)
```
GIVEN CommandRouter aktif dengan handler terdaftar untuk "help"
WHEN user mengirim pesan "!help"
THEN CommandHandler untuk "help" dipanggil dalam < 100ms

GIVEN tidak ada handler untuk command "unknown"
WHEN user mengirim "!unknown"  
THEN user menerima pesan "Command tidak dikenal" dalam < 500ms
```

### AC-004 (untuk FR-040, FR-041)
```
GIVEN sebuah FeatureModule baru dibuat mengikuti interface IFeatureModule
WHEN module didaftarkan ke FeatureRegistry
THEN semua handlers dalam module aktif tanpa restart platform
  DAN tidak ada feature module lain yang terpengaruh
```

---

## 7. Constraints & Assumptions

- **Neonize version**: Menggunakan versi stable terbaru, di-pin di `pyproject.toml`
- **Python version**: 3.13+ (memanfaatkan fitur terbaru: `type` statement, improved asyncio)
- **Single nomor WA per instance**: MVP tidak mendukung multi-session
- **WhatsApp ToS**: Developer bertanggung jawab atas penggunaan sesuai ToS

---

## 8. Traceability Matrix

| Req ID | Use Case | Feature | Test ID |
|--------|----------|---------|---------|
| FR-001 | UC-001 | session | TEST-SESSION-001 |
| FR-002 | UC-001 | session | TEST-SESSION-002 |
| FR-003 | UC-010 | session | TEST-SESSION-010 |
| FR-010 | UC-002 | messaging | TEST-MSG-001 |
| FR-020 | UC-003 | messaging | TEST-MSG-010 |
| FR-030 | UC-005 | commands | TEST-CMD-001 |
| FR-040 | UC-009 | core | TEST-CORE-001 |

---

## References

- [DOC-001: Product Vision](./01_product_vision.md)
- [DOC-003: Personas & Use Cases](./03_personas_and_use_cases.md)
- [DOC-011: SRS](./10_srs.md)
- [DOC-020: Testing Strategy](./18_testing_strategy.md)
