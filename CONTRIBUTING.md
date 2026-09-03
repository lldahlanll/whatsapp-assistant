# Contributing Guidelines

Terima kasih telah tertarik untuk berkontribusi pada proyek **WhatsApp Platform**! Proyek ini mengikuti standar engineering profesional untuk menjaga kualitas kode dan arsitektur tetap bersih.

---

## 📜 Development Rules

1. **Prinsip Arsitektur**: Semua perubahan harus mematuhi [Clean Architecture & DDD Principles](docs/05_architecture_overview.md). Jangan impor layer infrastruktur secara langsung ke domain layer.
2. **Type Annotations**: High coverage type hints bersifat wajib. Mypy harus pass dalam mode `strict`.
3. **Tests**: Setiap Pull Request yang menambahkan fitur atau memperbaiki bug HARUS menyertakan unit/integration test.
4. **No Direct Commits**: Semua perubahan harus melalui Pull Request (PR) ke branch `main`.

---

## 🔄 Pull Request Process

1. **Fork & Branch**
   Buat branch baru dari `main`:
   `git checkout -b feat/nama-fitur` atau `fix/nama-bug`

2. **Commit Convention**
   Ikuti format [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat(scope): ...`
   - `fix(scope): ...`
   - `docs(scope): ...`

3. **Pre-PR Verification**
   Sebelum push, jalankan verifikasi lokal:
   ```bash
   uv run ruff check .
   uv run mypy src
   uv run pytest
   ```

4. **Submit PR**
   Buka PR dengan penjelasan ringkas mengenai perubahan Anda dan sertakan link ke Issue/PRD terkait.

---

## 🔍 Code Review Checklist

Setiap PR akan direview berdasarkan kriteria:
- [ ] Apakah Clean Architecture dependency rule dipatuhi?
- [ ] Apakah `uv run ruff check` dan `mypy` pass tanpa peringatan?
- [ ] Apakah unit test ditambahkan dan test coverage >= 80%?
- [ ] Apakah dokumentasi (docstring/ADR) diperbarui jika ada keputusan teknis baru?
