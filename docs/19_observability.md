# DOC-021 · Observability & Logging Strategy

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** DevOps Engineer + Senior Developer  

---

## 1. Logging Framework & Standards

Platform ini menggunakan **`structlog`** untuk menghasilkan structured JSON log di lingkungan Production, dan colored console output untuk Development.

### Structured Log Format (JSON)
```json
{
  "timestamp": "2026-08-03T14:30:00.123456Z",
  "level": "info",
  "event": "message_received",
  "correlation_id": "req-9b1deb4d-3b7d-4144-9cd7-2994163ce480",
  "session_id": "sess-prod-01",
  "message_id": "3EB0C1234567890",
  "from_jid": "628123456789@s.whatsapp.net",
  "content_type": "text"
}
```

---

## 2. Log Levels & Rules

| Level | Penggunaan | Contoh |
|---|---|---|
| `DEBUG` | Langkah-langkah internal terperinci, hanya aktif saat troubleshooting | Parsing token, raw event dump |
| `INFO` | Transisi status normal, eksekusi use case | `session_connected`, `message_sent` |
| `WARNING` | Kondisi tak terduga yang dapat ditangani (resilient) | `unknown_command`, retry attempt #2 |
| `ERROR` | Aksi gagal tetapi sistem terus berjalan | `message_send_failed`, DB save error |
| `CRITICAL` | Kegagalan sistem fatal yang membutuhkan penghentian proses | `db_connection_failed`, invalid config |

---

## 3. Correlation ID Tracing

Setiap kali pesan masuk dari Neonize atau event dipicu, sebuah `correlation_id` unik (UUIDv4) dibuat dan dilekatkan pada konteks logger menggunakan `structlog.contextvars`. 

Semua log yang dihasilkan selama pemrosesan pesan tersebut akan secara otomatis membawa `correlation_id` yang sama untuk memudahkan analisis trace log.

---

## 4. Metrics & Monitoring Targets (Future Stack: Prometheus)

- **`whatsapp_messages_received_total`**: Counter total pesan masuk
- **`whatsapp_messages_sent_total`**: Counter total pesan terkirim
- **`whatsapp_message_processing_duration_seconds`**: Histogram latensi pemrosesan pesan
- **`whatsapp_session_connected_status`**: Gauge (1 = connected, 0 = disconnected)

---

## References

- [DOC-015: Error Handling](./15_error_handling.md)
- [DOC-018: Coding Standards](./16_coding_standards.md)
