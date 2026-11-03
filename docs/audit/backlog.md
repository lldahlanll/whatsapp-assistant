# Audit Backlog

Temuan audit yang **belum** atau **sengaja tidak** dikerjakan. Temuan yang sudah diperbaiki dicatat di
bagian "Selesai" sebagai referensi.

## Masih terbuka

### [Low] Skema belum punya FOREIGN KEY (Stage 2)
- `PRAGMA foreign_keys=ON` sudah aktif, tapi tidak ada constraint untuk ditegakkan.
- **Sengaja ditunda:** SQLite butuh rebuild tabel (batch) untuk `finance_transactions`, `finance_budgets`, dll.
  Jika data produksi sudah punya referensi yatim, migrasi bisa gagal saat startup. Semua penulisan lewat aplikasi
  dan sudah dicek per-owner, jadi risiko praktisnya kecil.
- **Prasyarat sebelum dikerjakan:** jalankan `scripts/reconcile_finance.py` di DB produksi dan pastikan tidak ada
  temuan "merujuk rekening/kategori yang tidak ada".

### [Low] `Numeric(18,2)` disimpan sebagai REAL di SQLite (Stage 2) — sebagian dimitigasi
- Dimitigasi: nominal dibulatkan 2 desimal dan dibatasi maks 1 triliun; cek saldo memakai `round(…, 2)`.
- Sisa: nilai mentah di DB tetap float (mis. 0.7999999999999999). Perbaikan penuh = simpan satuan integer (migrasi besar).
  Rupiah bulat tidak terdampak.

### [Low] Rekening yang dihapus dengan saldo ≠ 0 (Stage 2) — perilaku diterima
- Saldo tidak lagi dihitung di total, dan transaksi pada rekening itu tidak bisa di-reverse ("Rekening ... tidak ditemukan").
- Pengguna sudah diberi tahu sisa saldo pada konfirmasi hapus. Opsi lanjutan: tolak hapus bila saldo ≠ 0.
- Koreksi catatan audit sebelumnya: pesan "saldo tidak mencukupi" yang menyesatkan hanya muncul pada kondisi
  balapan, bukan pada alur normal.

### [Low] Lain-lain
- `get_total_balance` menjumlah lintas mata uang (aman selama hanya IDR).
- MikroTik: konfigurasi default tetap HTTP tanpa verifikasi sertifikat. Saat ini hanya **peringatan saat startup**;
  memaksa HTTPS menunggu konfirmasi bahwa router mendukung `www-ssl` dengan sertifikat valid.
  Semua anggota grup yang masuk `NETWORK_ALLOWED_JIDS` bisa membaca data router (disengaja).
- Belum direview: `parser.py`, `formatter.py`, `finance_fast_path`, logika budget, handler `!finance`,
  `transcriber.py`, `sqlite_store.py`, `gateway.py`, `mikrotik/toolbox.py`.
- Scan CVE dependensi belum dijalankan (`pip-audit` tidak tersedia di mesin audit).

## Selesai

| Temuan | Perbaikan |
|---|---|
| Stage 2 — hapus transaksi = hard delete | Soft delete (`deleted_at`, migrasi `f1a2b3c4d5e6`); baris tetap ada sebagai jejak audit, saldo tetap dikembalikan, dua penghapusan bersamaan hanya mengubah saldo sekali |
| Stage 2 — tidak ada rekonsiliasi | `scripts/reconcile_finance.py` (baca-saja) |
| Stage 2 — `_pending_confirmations` tumbuh tanpa batas | Entri kedaluwarsa dibuang |
| Stage 2 — cek saldo float | `round(balance+delta, 2) >= 0`; nominal dinormalkan & dibatasi |
| Stage 1 — rate limit AI per chat saja | Batas per pengirim di grup (`AI_RATE_LIMIT_PER_USER_MAX_REQUESTS`, default 3); jendela kedaluwarsa dibersihkan |
| Stage 1 — gambar tanpa batas piksel | Batas 50 MP di `MediaProcessor.compress_image`. Catatan: fungsi ini saat ini tidak dipanggil di mana pun, jadi risikonya memang belum aktif |
| Stage 1 — MikroTik HTTP/tanpa verifikasi | Peringatan saat startup (lihat "Masih terbuka") |
