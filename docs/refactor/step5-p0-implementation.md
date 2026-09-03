# Step 5 — Laporan Implementasi P0 (Critical Refactoring)

Dokumen ini mencatat seluruh perubahan dan hasil implementasi P0 (Critical Token Optimization) pada codebase `whatsapp-assistant`.

---

## 1. Fitur & Komponen P0 yang Berhasil Diimplementasikan

1. **Intent Classification SEBELUM History Fetch**
   - Diimplementasikan di [`AIReplyUseCase.execute()`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/application/use_cases/ai_reply.py#L144-L180).
   - Intent dievaluasi pertama kali sebelum DB history ditarik.
   - Dilengkapi fallback guard: jika router gagal, fallback otomatis ke intent `"chat"`. Jika history fetch gagal, alur tetap berjalan tanpa history (tidak melempar error ke user).

2. **Pre-Router Fast Path (`pre_router.py`)**
   - Menambahkan classifier ringan untuk kata-kata sapaan dan ucapan simpel ("hallo", "hai", "makasih", "siapa kamu", dll).
   - Menghasilkan intent `"simple_chat"` dengan `history=0` dan `tools=0`.
   - Menggunakan guard non-agresif: jika pesan mengandung kata kunci finansial atau jaringan (seperti `"halo, saldo BCA saya berapa?"`), pre-router menolak fast path dan menyerahkan ke keyword classifier penuh.

3. **Dynamic ContextPolicy Terpusat (`context_policy.py`)**
   - Menambahkan dataclass `ContextPolicy` dan `ContextPolicyManager`.
   - Mengatur limit history secara terpusat berdasarkan intent yang dikonfigurasi via environment variable (`Settings`):
     - `simple_chat`: `history_limit = 0`
     - `chat`: `history_limit = settings.ai_chat_history_limit` (default 3)
     - `finance`: `history_limit = settings.ai_finance_history_limit` (default 5)
     - `network`: `history_limit = settings.ai_network_history_limit` (default 3)
     - `full`: `history_limit = settings.ai_complex_history_limit` (default 8)

4. **Dynamic Tool Selection per Sub-Domain (`tool_policy.py`)**
   - Finance dan MikroTik tools tidak lagi dikirim secara keseluruhan (8 atau 16 tools).
   - Tools difilter berdasarkan kata kunci spesifik dalam query:
     - Pertanyaan saldo (`"saldo BCA saya berapa?"`) → Hanya mengirim `[finance_get_balance]` (1 tool).
     - Pertanyaan status router (`"CPU MikroTik berapa?"`) → Hanya mengirim `[mikrotik_get_health, mikrotik_get_traffic]` (2 tools).

5. **Token & LLM Observability Logging (`AI_METRICS`)**
   - Menambahkan [`metrics_logger.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/metrics_logger.py).
   - `AIService` secara otomatis mencetak log terstruktur `AI_METRICS` untuk setiap panggilan LLM.
   - Metrik yang dicatat: `request_id`, `jid`, `intent`, `model`, `provider`, `history_message_count`, `history_chars`, `system_prompt_chars`, `tool_count`, `tool_definition_chars`, `tool_result_chars`, `input_tokens`, `output_tokens`, `total_tokens`, `llm_call_number`, `total_llm_calls`, `latency_ms`.
   - Menjaga kerahasiaan: **TIDAK mencetak isi pesan mentah** maupun hasil tool secara lengkap.

---

## 2. Berkas yang Dibuat / Diubah

- **Dibuat**:
  - [`src/whatsapp_platform/infrastructure/ai/pre_router.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/pre_router.py)
  - [`src/whatsapp_platform/infrastructure/ai/context_policy.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/context_policy.py)
  - [`src/whatsapp_platform/infrastructure/ai/tool_policy.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/tool_policy.py)
  - [`src/whatsapp_platform/infrastructure/ai/metrics_logger.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/metrics_logger.py)
- **Diubah**:
  - [`src/whatsapp_platform/infrastructure/config/settings.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/config/settings.py)
  - [`src/whatsapp_platform/infrastructure/ai/constants.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/constants.py)
  - [`src/whatsapp_platform/application/use_cases/ai_reply.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/application/use_cases/ai_reply.py)
  - [`src/whatsapp_platform/infrastructure/ai/ai_service.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py)
