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
