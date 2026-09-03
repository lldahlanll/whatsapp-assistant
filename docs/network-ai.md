# Network AI & MikroTik Integration

Modul **Network AI & MikroTik** menambahkan kapabilitas monitoring, observasi lalu lintas, pengecekan DHCP, audit firewall, dan asesmen keamanan jaringan MikroTik RouterOS v7 secara read-only melalui WhatsApp.

---

## 1. Arsitektur

```
WhatsApp Inbound Message
        │
        ▼
   Neonize Gateway
        │
        ▼
  Event Bus (MessageReceived)
   ┌────┴──────────────────────────────┐
   ▼                                   ▼
NetworkMessageHandler          CommandRouter (!network / !net)
   │                                   │
   ├─ Intent Detector                  │
   ├─ Permission Guard                 ├─ Permission Guard
   ├─ Rate Guard                       ├─ Rate Guard
   └─────────────────┬─────────────────┘
                     │
                     ▼
              NetworkToolbox
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   MikroTikCache           MikroTikRestClient (httpx)
                                 │ (HTTP Basic Auth)
                                 ▼
                     MikroTik RouterOS v7 (REST API)
```

---

## 2. Fitur & Tools Read-Only

| Tool | Fungsi | Cache TTL |
|---|---|---|
| `get_system_health` | CPU, RAM, Uptime, Suhu, Voltase, Board info | 30 detik |
| `get_interfaces` | Status UP/DOWN, RX/TX, Packets, Errors, Drops | Live |
| `get_interface_traffic` | Bandwidth snapshot per interface / WAN | Live |
| `get_dhcp_leases` | IP, MAC, Hostname, status bound client | 15 detik |
| `get_firewall_rules` | Inspeksi filter rules dan NAT | 60 detik |
| `get_routes` | Tabel routing IP dan gateway | 30 detik |
| `get_dns_status` | Server DNS, Cache, DoH | 30 detik |
| `get_logs` | Catatan aktivitas router terbaru | Live (safe limit) |
| `calculate_health_score` | Skor kesehatan transparan (0-100) berbobot | Sesuai health |
| `security_audit` | Asesmen keamanan port management, DNS, firewall | 60 detik |

---

## 3. Konfigurasi Environment Variables

Tambahkan ke file `.env`:

```env
# ── MikroTik REST API & Network AI ─────────────────────────────
MIKROTIK_ENABLED=true
MIKROTIK_HOST="192.168.88.1"
MIKROTIK_PORT=80              # 80 untuk HTTP / 443 untuk HTTPS (service www / www-ssl)
MIKROTIK_USERNAME="ai-readonly"
MIKROTIK_PASSWORD="SuperSecretPassword"
MIKROTIK_USE_SSL=false        # true jika menggunakan HTTPS
MIKROTIK_VERIFY_SSL=false     # true jika HTTPS memakai sertifikat CA valid
MIKROTIK_TIMEOUT=5.0          # Timeout per request (detik)

# Whitelist JID yang diizinkan (kosongkan untuk mengizinkan semua pengguna)
NETWORK_ALLOWED_JIDS="628123456789@s.whatsapp.net,12036301234567890@g.us"

# TTL Caching (detik)
NETWORK_CACHE_TTL_SYSTEM=30
NETWORK_CACHE_TTL_FIREWALL=60
NETWORK_CACHE_TTL_ROUTES=30
NETWORK_CACHE_TTL_DHCP=15
```

---

## 4. Cara Penggunaan

### A. Perintah Langsung (Commands)
- `!network health` atau `!net status` — Laporan kesehatan & skor router
- `!network traffic [iface]` — Cek traffic interface (misal: `!network traffic ether1`)
- `!network security` — Audit keamanan router
- `!network dhcp [keyword]` — Cek client DHCP aktif
- `!network firewall` — Ringkasan filter & NAT
- `!network routes` — Cek tabel routing
- `!network logs [topik]` — Cek log terbaru

### B. Bahasa Alami (Natural Language)
Bot secara otomatis mendeteksi kata kunci pertanyaan jaringan:
- *"cek mikrotik"* ➔ Network Health & Score
- *"berapa bandwidth sekarang?"* ➔ Traffic WAN & Interface
- *"ada masalah jaringan?"* ➔ Health & Error indicators
- *"cek security mikrotik"* ➔ Security Audit & Remediasi
- *"siapa saja yang connect wifi?"* ➔ DHCP client leases
- *"lihat firewall"* ➔ Ringkasan Firewall

---

## 5. Model Keamanan (Security Boundary)

1. **Strictly READ-ONLY**: Klien HTTP hanya memiliki method `GET`. Tidak ada endpoint `POST`, `PUT`, `PATCH`, `DELETE`, atau eksekusi script arbitrary yang diekspos.
2. **Kredensial Aman**: Password router tidak pernah dicatat ke dalam log (sanitized structured logging).
3. **Access Control**: Otorisasi berbasis whitelist WhatsApp JID.
4. **Rate Limiting**: Sliding window 60 detik per pengguna untuk mencegah overload pada REST API MikroTik.
