# 📚 Enterprise Documentation Index: Neonize Platform

> **Status:** Active Implementation (Core Platform v0.1.0 Released)  
> **Version:** 2.1.0  
> **Last Updated:** 2026-08-07  

Selamat datang di pusat dokumentasi resmi **Neonize Enterprise Platform**. Seluruh dokumentasi teknis, keputusan arsitektur, spesifikasi fitur, dan panduan operasional terorganisir di bawah ini:

---

## 🗂️ Struktur Direktori Dokumentasi

```text
docs/
├── 📁 01-project/          # Project Vision, Glossary, Personas & Onboarding
├── 📁 02-prd/              # PRD & Software Requirement Specifications (SRS)
├── 📁 03-architecture/     # Clean Architecture, C4 Diagrams & Domain Model
├── 📁 04-api/              # REST API Specs, Webhooks & Event Catalog
├── 📁 05-database/         # ERD, DB Schema, Migrations & Vector DB Setup
├── 📁 06-features/         # Spesifikasi Per-Fitur (Session, AI, RAG, Plugins)
├── 📁 07-deployment/       # Docker, Kubernetes, Helm & CI/CD Pipelines
├── 📁 08-monitoring/       # Logging (Structlog), Sentry, Prometheus & Grafana
├── 📁 09-testing/          # Testing Strategy Handbook & Coverage Rules (90%)
├── 📁 10-contributing/     # Developer Handbook, Coding Standards & Git Rules
├── 📁 11-changelog/        # SemVer Strategy & Release Notes
├── 📁 12-roadmap/          # Master Development Roadmap (Milestone 1 - 10)
├── 📁 13-decision-log/     # Architecture Decision Records (ADRs)
├── 📁 14-runbook/          # Operational SOPs, Backup & Emergency Recovery
├── 📁 15-troubleshooting/ # Guide Penanganan Error Common Issues
├── 📁 16-security/         # Security Model, Secret Management & E2EE Policy
└── 📁 17-faq/              # Frequently Asked Questions (Developer & Ops)
```

---

## 📋 Deskripsi & Isi Setiap Folder

### 01. `01-project/` (Project Vision & Onboarding)
* **Isi:** Visi produk, tujuan bisnis platform, domain glossary (istilah JID, Whatsmeow, Session), deskripsi persona pengguna, dan panduan onboarding cepat (*Quick Start*) bagi pengembang baru.

### 02. `02-prd/` (Product Requirement Documents)
* **Isi:** Dokumen PRD utama, Software Requirements Specification (SRS), daftar *Functional Requirements* & *Non-Functional Requirements*, serta pemetaan User Stories.

### 03. `03-architecture/` (System Architecture & Design)
* **Isi:** Cetak biru arsitektur sistem Clean Architecture, C4 Diagrams (Context, Container, Component, Code), pemetaan domain model (Entities, Value Objects), dan strategi Dependency Injection (`Dishka`).

### 04. `04-api/` (API Contracts & Specs)
* **Isi:** Spesifikasi OpenAPI/Swagger untuk REST Admin API, kontrak JSON Outgoing Webhooks, dan Event Catalog (katalog domain event & Neonize event).

### 05. `05-database/` (Data Architecture & Storage)
* **Isi:** Diagram ERD Relasional, skema tabel PostgreSQL/SQLite, panduan migrasi DB menggunakan Alembic, spesifikasi penyimpan sesi SQLite Whatsmeow (`store.db`), dan konfigurasi Vector DB (Qdrant).

### 06. `06-features/` (Feature Specifications)
* **Isi:** Spesifikasi rinci per modul fitur: *Session Management*, *Messaging Engine*, *Media Converter*, *Command Router*, *AI Integration*, *Hybrid RAG Engine*, dan *Dynamic Plugin System*.

### 07. `07-deployment/` (Infrastructure & Deployment)
* **Isi:** Panduan Docker multi-stage build, konfigurasi `docker-compose.yml`, manifest Kubernetes (StatefulSet, Service, Secret), Helm Charts, dan spesifikasi pipeline CI/CD GitHub Actions.

### 08. `08-monitoring/` (Observability & Monitoring)
* **Isi:** Katalog Prometheus Metrics, format JSON `structlog`, panduan konfigurasi Sentry error tracking, template Grafana Dashboard, dan spesifikasi liveness/readiness healthcheck.

### 09. `09-testing/` (Testing Strategy & QA)
* **Isi:** Panduan strategi pengujian lengkap (Unit, Integration, API, Performance, Load, Stress, Regression, E2E), panduan fixture `factory-boy`/`faker`, dan aturan enforcement coverage minimum 90%.

### 10. `10-contributing/` (Developer Handbook & Style Guide)
* **Isi:** Developer Handbook lengkap, aturan Coding Standard (Ruff/Mypy), alur kerja Git (Trunk-Based), aturan Conventional Commits, penamaan branch, dan checklist Code Review PR.

### 11. `11-changelog/` (Release Notes & Versioning)
* **Isi:** Kebijakan Semantic Versioning (`vX.Y.Z`), catatan rilis resmi per versi, panduan migrasi antar versi (breaking changes), dan konfigurasi `git-cliff`.

### 12. `12-roadmap/` (Master Development Roadmap)
* **Isi:** Roadmap pembangunan proyek 10 Milestone dari awal hingga produksi, beserta checklist penyelesaian per milestone.

### 13. `13-decision-log/` (Architectural Decision Records)
* **Isi:** Indeks catatan keputusan arsitektur (ADR), seperti alasan pemilihan Neonize dibanding Puppeteer, SQLAlchemy 2.0 dibanding Tortoise ORM, Qdrant dibanding Chroma DB, dll.

### 14. `14-runbook/` (Operational Runbooks)
* **Isi:** Standard Operating Procedure (SOP) untuk tim DevOps & Sysadmin, panduan manual QR re-pairing, langkah backup & restore database/session, serta skenario pemulihan darurat (*Disaster Recovery*).

### 15. `15-troubleshooting/` (Debugging & Problem Solving)
* **Isi:** Panduan pemecahan masalah untuk error umum (misal: *Session Disconnected*, *SQLite Database Lock*, *Rate Limit WA Server*, *Audio Opus Conversion Error*).

### 16. `16-security/` (Security & Privacy)
* **Isi:** Model keamanan aplikasi, kebijakan enkripsi data (E2EE WhatsApp & DB encryption), manajemen rahasia (`SecretStr`), serta laporan pemindaian kerentanan dependensi (`trufflehog`/`pip-audit`).

### 17. `17-faq/` (Frequently Asked Questions)
* **Isi:** Jawaban atas pertanyaan yang sering diajukan oleh pengembang, kontributor, dan tim operasional terkait limitasi API WhatsApp, kustomisasi prompt AI, lisensi, dan performa.
