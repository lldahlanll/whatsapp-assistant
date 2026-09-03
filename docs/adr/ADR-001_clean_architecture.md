# ADR-001 · Menggunakan Clean Architecture + Feature-Based Structure

> **Status:** Accepted  
> **Date:** 2026-08-03  
> **Deciders:** Senior Architect, Lead Developer  

---

## Context

Kita perlu memilih struktur arsitektur yang akan menjadi fondasi platform ini selama bertahun-tahun.

## Decision

Menggunakan **Clean Architecture** sebagai prinsip layering (dependency rule) dikombinasikan dengan **Feature-Based (Vertical Slice) Structure** untuk pengorganisasian folder.

## Consequences

**Positif:**
- Domain logic 100% testable tanpa dependency eksternal
- Fitur baru tidak perlu menyentuh kode yang sudah ada
- Onboarding developer baru lebih cepat (folder per fitur, bukan per layer)

**Negatif:**
- Lebih banyak file dan abstraksi dari script sederhana
- Learning curve bagi developer yang terbiasa dengan MVC

## Alternatives Considered

| Alternatif | Alasan Tidak Dipilih |
|------------|---------------------|
| MVC (Model-View-Controller) | Tidak cocok untuk event-driven messaging platform |
| Pure Layered Architecture | Semua fitur tersebar di semua layer — navigasi sulit |
| Hexagonal Architecture | Secara konsep sama dengan Clean Architecture, terlalu banyak terminologi baru |
