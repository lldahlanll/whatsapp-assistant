# DOC-001 · Product Vision & Goals Document

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Product Architect  

---

## 1. Vision Statement

> **"Menjadi platform otomasi WhatsApp berbasis Python yang paling clean, scalable, dan mudah dikembangkan — memberikan fondasi yang kokoh bagi siapapun yang ingin membangun intelligent messaging automation tanpa mengorbankan kualitas kode."**

---

## 2. Mission Statement

Membangun sebuah platform production-grade di atas Neonize + Python yang:

- **Clean**: Setiap baris kode memiliki alasan yang jelas dan terstruktur.
- **Scalable**: Mampu menangani pertumbuhan fitur, pengguna, dan kompleksitas tanpa refactor besar.
- **Maintainable**: Developer baru bisa memahami dan berkontribusi dalam hitungan jam, bukan minggu.
- **Extensible**: Fitur baru dapat ditambahkan sebagai modul independen tanpa menyentuh core.

---

## 3. Problem Statement

### 3.1 Masalah yang Ada Saat Ini

Sebagian besar implementasi bot WhatsApp berbasis Python saat ini memiliki masalah struktural:

| Masalah | Dampak |
|---------|--------|
| Semua logika dalam satu file `main.py` | Tidak bisa discale, sulit di-debug |
| Tidak ada separation of concerns | Perubahan kecil memiliki efek domino |
| Tidak ada type safety | Bug tersembunyi di runtime |
| Tidak ada test | Perubahan apa pun bisa membreak fitur lain |
| Konfigurasi tersebar | Tidak aman untuk deployment |
| Tidak ada error handling strategy | Crash tanpa recovery |
| Coupling ke library eksternal langsung | Sulit ganti library bila ada breaking change |

### 3.2 Solusi Yang Ditawarkan

Platform ini menyelesaikan semua masalah di atas dengan menerapkan:

- **Clean Architecture** → Separation of concerns yang tegas antar layer
- **Feature-Based Structure** → Setiap fitur adalah modul independen
- **Dependency Injection** → Decoupling antar komponen
- **Full Type Hints + Mypy** → Bug terdeteksi saat development
- **Comprehensive Testing** → Confidence dalam setiap perubahan
- **Neonize sebagai Infrastructure** → Tidak pernah menyentuh Neonize langsung di business logic

---

## 4. Target Audience

### Primary Users (Direct Developers)
- Python developer yang ingin membangun WhatsApp automation serius
- Tim kecil yang membutuhkan platform messaging yang bisa dikembangkan bersama

### Secondary Users (End Users of Features)
- Bisnis yang menggunakan bot untuk customer service
- Tim yang menggunakan bot untuk notifikasi internal
- Developer yang ingin integrasi AI dengan WhatsApp

---

## 5. Business Goals

### 5.1 Jangka Pendek (0–3 Bulan)
- [ ] MVP platform dengan core features berjalan stabil
- [ ] Dokumentasi lengkap (semua 28 dokumen)
- [ ] Test coverage >= 80%
- [ ] Deploy sukses di Docker environment
- [ ] QR pairing, send/receive text, command routing berfungsi

### 5.2 Jangka Menengah (3–12 Bulan)
- [ ] Plugin/feature module system yang matang
- [ ] AI integration layer (LLM-agnostic)
- [ ] Scheduler & broadcast system
- [ ] REST API layer untuk integrasi eksternal
- [ ] Dashboard monitoring sederhana

### 5.3 Jangka Panjang (1–3 Tahun)
- [ ] Multi-session management (lebih dari 1 nomor WhatsApp)
- [ ] Analytics pipeline
- [ ] Horizontal scaling via containerization
- [ ] Community plugin marketplace

---

## 6. Success Metrics (KPIs)

| Metric | Target |
|--------|--------|
| Test coverage | >= 80% |
| Message processing latency (p95) | < 500ms |
| Session recovery time after disconnect | < 30 detik |
| Time to add new feature module | < 2 jam untuk dev berpengalaman |
| Mypy strict pass | 100% |
| CI pipeline duration | < 5 menit |
| Time to onboard new developer | < 1 jam |

---

## 7. Scope

### 7.1 Dalam Scope (MVP)
- Session management (QR pairing, reconnect, disconnect graceful)
- Send & receive: text, media (image, video, document, audio)
- Command routing (prefix-based, regex-based)
- Plugin/handler module system
- Structured logging
- Configuration via environment variables
- Docker-based deployment
- Unit & integration tests

### 7.2 Luar Scope (MVP, untuk versi berikutnya)
- Web dashboard / admin panel
- Multi-tenant support
- Payment integration
- Webhook inbound dari WhatsApp Business API resmi
- iOS/Android native SDK

### 7.3 Explicit Non-Goals
- Bukan pengganti WhatsApp Business API resmi
- Bukan tool untuk spam atau automation yang melanggar ToS WhatsApp
- Bukan framework general-purpose messaging (fokus ke WhatsApp via Neonize)

---

## 8. Constraints & Assumptions

### Constraints
| Constraint | Deskripsi |
|------------|-----------|
| WhatsApp ToS | Penggunaan harus sesuai ToS. Spam, flooding, dan abuse dilarang. |
| Neonize stability | Bergantung pada library pihak ketiga; breaking change mungkin terjadi |
| Session limit | Satu session = satu nomor WhatsApp aktif |
| Python 3.13+ | Minimum Python version yang didukung |

### Assumptions
- Developer memiliki akses ke nomor WhatsApp aktif untuk testing
- Environment target adalah Linux (Docker container)
- Internet connection stabil diasumsikan untuk koneksi ke WhatsApp server
- Database default: SQLite untuk development, PostgreSQL untuk production

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Neonize breaking changes | Medium | High | Version pinning + adapter pattern |
| WhatsApp banning session | Low | High | Rate limiting, human-like delays |
| Neonize tidak maintained | Low | High | Abstraction layer sehingga bisa diganti |
| Overengineering | Medium | Medium | Start simple, refactor sesuai kebutuhan |

---

## 10. References

- [Neonize GitHub](https://github.com/krypton-byte/neonize)
- [DOC-002: Domain Glossary](./02_domain_glossary.md)
- [DOC-004: PRD](./04_prd.md)
