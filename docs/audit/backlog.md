# Audit Backlog

Temuan audit yang sengaja belum dikerjakan. Diurutkan per severity.

## Stage 1 — Keamanan

### [Medium] MikroTik default HTTP tanpa verifikasi sertifikat
- **Lokasi:** `infrastructure/config/settings.py` (`mikrotik_use_ssl=False`, `mikrotik_verify_ssl=False`), `infrastructure/mikrotik/client.py`.
- **Dampak:** kredensial router dikirim cleartext (Basic Auth) lewat jaringan.
- **Catatan:** `network/permission.py` mengizinkan semua anggota grup yang masuk `NETWORK_ALLOWED_JIDS` membaca data router (disengaja, tapi perlu disadari).
- **Syarat sebelum dikerjakan:** pastikan router mendukung `www-ssl` dengan sertifikat valid. Memaksa HTTPS tanpa itu akan memutus fitur network.
- **Saran:** wajibkan HTTPS + `verify_ssl=true` saat `APP_ENV=production`, atau beri peringatan jelas saat startup.

### [Low] Rate limit AI per chat, bukan per pengguna
- **Lokasi:** `features/ai/rate_guard.py` (`check_and_record(chat_jid)`), dipanggil dari `features/ai/handler.py`.
- **Dampak:** satu anggota grup dapat menghabiskan kuota AI seluruh grup, sekaligus biaya token.
- **Saran:** tambah jendela kedua per `(chat, sender)` di samping batas per chat.

### [Low] Pemrosesan gambar tanpa batas jumlah piksel
- **Lokasi:** `shared/utils/media_processor.py` (`compress_image`).
- **Dampak:** ukuran file dibatasi (5 MB) tetapi resolusi tidak; gambar kecil beresolusi sangat besar (decompression bomb) bisa memakan memori besar.
- **Saran:** set `Image.MAX_IMAGE_PIXELS` yang wajar dan tolak gambar di atas batas sebelum decode penuh.

## Stage 2 — Integritas data keuangan

### [Medium] Hapus transaksi adalah hard delete
- **Lokasi:** `finance_repo.py` `delete_transaction`.
- Menghapus jejak audit dan boleh membuat saldo minus (perilaku lama dipertahankan). Reversal sudah tersedia sebagai jalur yang aman.
- **Saran:** jadikan soft delete / arahkan ke reversal; minimal snapshot seperti pada reset.

### [Low] `Numeric(18,2)` disimpan sebagai REAL di SQLite
- Nilai mentah bisa 0.9999999999999999 setelah akumulasi pecahan; cek `balance + delta >= 0` bisa salah di batas.
- Rupiah bulat aman. **Saran:** bulatkan/validasi nominal, atau simpan dalam satuan integer.

### [Low] Rekening yang dihapus (soft delete) dengan saldo ≠ 0
- Saldo hilang dari total; reversal/pemasukan ke rekening itu gagal dengan pesan "saldo tidak mencukupi" yang menyesatkan.

### [Low] Lain-lain
- `FinanceToolExecutor._pending_confirmations` tidak pernah dibersihkan (tumbuh pelan).
- `get_total_balance` menjumlah lintas mata uang (aman selama hanya IDR).
- Tidak ada rekonsiliasi `account.balance` vs akumulasi transaksi (usul: skrip baca-saja).
- Skema belum punya FOREIGN KEY (pragma `foreign_keys=ON` sudah aktif, tapi belum ada constraint untuk ditegakkan).
- Belum direview: `parser.py`, `formatter.py`, `finance_fast_path`, logika budget, handler `!finance`.
