# Step 1 — Audit Codebase Token Efficiency

Audit ini mendokumentasikan secara detail seluruh komponen AI pada codebase `whatsapp-assistant`, lokasi persis file + line range, mekanisme kerja, ukuran context default, serta titik-titik pemborosan token yang teridentifikasi.

---

## 1. Lokasi & Deskripsi Komponen AI

### A. AIMessageHandler
- **File & Line Range**: [`src/whatsapp_platform/features/ai/handler.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/features/ai/handler.py#L33-L206)
- **Fungsi**: Event listener yang menerima `MessageReceived` domain event, memvalidasi guard (idempotency, self message, non-text, prefix command, phone core extractor/Customer Lookup, config enabled, group chat mention/reply guard, per-chat rate guard), memunculkan indikator typing, lalu memanggil `AIReplyUseCase.execute()`.
- **Yang Sudah Dikelola**: Menolak pesan non-teks dan pesan command (`!`) sebelum memanggil AI.

### B. AIReplyUseCase
- **File & Line Range**: [`src/whatsapp_platform/application/use_cases/ai_reply.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/application/use_cases/ai_reply.py#L102-L252)
- **Fungsi**: Orchestrator per-request untuk mengambil riwayat percakapan dari DB, melakukan prapemrosesan pesan, menentukan intent, menyusun list `ProviderMessage` dengan role separation native, memanggil `AIService.generate_reply()` / `generate_reply_with_tools()`, dan menyimpan hasil ke context cache.
- **Konfigurasi Intent Default**:
  - `chat`: `AI_SYSTEM_PROMPT`, tools: `None`
  - `finance`: `AI_FINANCE_SYSTEM_PROMPT`, tools: `FINANCE_TOOLS` (8 tools)
  - `network`: `AI_NETWORK_SYSTEM_PROMPT`, tools: `MIKROTIK_TOOLS` (8 tools)
  - `full`: `AI_FULL_SYSTEM_PROMPT`, tools: `MIKROTIK_TOOLS + FINANCE_TOOLS` (16 tools)

### C. Intent Classifier (`classify_intent`)
- **File & Line Range**: [`src/whatsapp_platform/infrastructure/ai/constants.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/constants.py#L145-L186)
- **Fungsi**: Keyword-based intent classification menggunakan substring matching sederhana (case-insensitive) terhadap dua set kata kunci:
  - **FINANCE_KEYWORDS** (28 keywords): `bayar`, `beli`, `saldo`, `transfer`, `pengeluaran`, `pemasukan`, `budget`, `catat`, `catet`, `dompet`, `keuangan`, `utang`, `cicilan`, `gaji`, `tabungan`, `rekap`, `uang`, `duit`, `rupiah`, `pembayaran`, `nota`, `struk`, `transaksi`, `belanja`, `anggaran`, `kategori`, `jual`, `mutasi`.
  - **NETWORK_KEYWORDS** (29 keywords): `internet`, `router`, `mikrotik`, `wifi`, `lambat`, `koneksi`, `bandwidth`, `firewall`, `jaringan`, `putus`, `gangguan`, `sinyal`, `lemot`, `gaada sinyal`, `indihome`, `biznet`, `myrepublic`, `astinet`, `health`, `cpu`, `speed`, `traffic`, `interface`, `port`, `dhcp`, `dns`, `uptime`, `restart`, `reboot`, `speedtest`, `routeros`.
- **Logika Intent**:
  - `has_finance and has_network` → `"full"`
  - `has_finance` → `"finance"`
  - `has_network` → `"network"`
  - Tidak ada yang match → `"chat"`

### D. Generation Methods (`generate_reply` & `generate_reply_with_tools`)
- **File & Line Range**: [`src/whatsapp_platform/infrastructure/ai/ai_service.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py#L296-L404)
- **Fungsi**:
  - `generate_reply`: Memanggil provider tunggal tanpa tools via fallback strategy & key pool loop.
  - `generate_reply_with_tools`: Menjalankan agentic loop (hingga `max_tool_iterations=5`). Jika LLM mengembalikan `tool_calls`, dipanggil via `CompositeToolExecutor`, hasilnya di-append sebagai role `tool`, lalu di-loop kembali ke LLM.

### E. AI Providers / Clients
- **File & Line Range**:
  - Gemini Adapter: [`src/whatsapp_platform/infrastructure/ai/providers/gemini.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/providers/gemini.py#L122-L241)
  - Groq Adapter: [`src/whatsapp_platform/infrastructure/ai/providers/groq.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/providers/groq.py#L91-L214)
  - OpenRouter Adapter: [`src/whatsapp_platform/infrastructure/ai/providers/openrouter.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/providers/openrouter.py#L49-L130)
- **Mekanisme**: Membawa retry & circuit breaker per-key (`KeyPool`), dengan fallback urutan default `gemini` -> `groq` -> `openrouter`.

### F. Context / History Repository & Context Cache
- **Database History Repository**: [`src/whatsapp_platform/infrastructure/database/repositories/message_repo.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/database/repositories/message_repo.py#L72-L85) & [`src/whatsapp_platform/application/use_cases/get_conversation.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/application/use_cases/get_conversation.py#L12-L18)
- **Context Cache (SQLite & In-Memory)**: [`src/whatsapp_platform/infrastructure/ai/sqlite_store.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/sqlite_store.py#L112-L160) & [`src/whatsapp_platform/infrastructure/ai/ai_service.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py#L139-L185)
- **Dual State Context Problem**:
  - `AIReplyUseCase.execute` selalu mengambil `20` pesan terakhir dari Database PostgreSQL/SQLite `messages` table via `GetConversationHistoryUseCase`.
  - Selain itu, `AIService` juga memiliki `append_to_context` yang menyimpan ke in-memory cache + SQLite `chat_context` table (`_max_context_messages = 20`).

### G. Tool Registries
- **MikroTik Tools (8 tools)**: [`src/whatsapp_platform/infrastructure/mikrotik/tool_schema.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/mikrotik/tool_schema.py#L95-L199)
  - `mikrotik_get_health`, `mikrotik_get_traffic`, `mikrotik_get_dhcp_leases`, `mikrotik_audit_security`, `mikrotik_get_firewall`, `mikrotik_get_routes`, `mikrotik_get_logs`, `mikrotik_get_connections`.
- **Finance Tools (8 tools)**: [`src/whatsapp_platform/infrastructure/finance/tool_schema.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/finance/tool_schema.py#L7-L239)
  - `finance_add_income`, `finance_add_expense`, `finance_transfer`, `finance_get_balance`, `finance_get_monthly_report`, `finance_get_transactions`, `finance_get_expense_summary`, `finance_create_account`.
- **Composite Tool Executor**: [`src/whatsapp_platform/infrastructure/ai/composite_executor.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/composite_executor.py#L20-L57)

### H. System Prompts saat Ini
- **File & Line Range**: [`src/whatsapp_platform/infrastructure/ai/constants.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/constants.py#L37-L143)
  - `AI_SYSTEM_PROMPT`: 565 karakter (~140 token)
  - `AI_NETWORK_SYSTEM_PROMPT`: 1.250 karakter (~310 token)
  - `AI_FINANCE_SYSTEM_PROMPT`: 1.450 karakter (~360 token)
  - `AI_FULL_SYSTEM_PROMPT`: 2.100 karakter (~520 token)

### I. Agentic Tool Execution Loop
- **File & Line Range**: [`src/whatsapp_platform/infrastructure/ai/ai_service.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py#L340-L403)
- **Mekanisme**: Melakukan loop hingga 5 iterasi. Tool output dikembalikan secara mentah (JSON string langsung dari response MikroTik API atau Finance DB Query) tanpa kompresi / compaction.

### J. Database Conversation History Schema & Queries
- **Model**: [`src/whatsapp_platform/infrastructure/database/models.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/database/models.py) (`MessageModel`)
- **Query**: `SELECT * FROM messages WHERE chat_jid = ? ORDER BY timestamp DESC LIMIT 20` (dalam `SQLAlchemyMessageRepository.get_chat_messages`).

### K. Lokasi Pemanggilan LLM Langsung
- Hanya ada 1 pintu utama pemanggilan LLM pada application level: `AIService._call_provider_with_retry` ([`src/whatsapp_platform/infrastructure/ai/ai_service.py:191`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py#L191)), yang kemudian diteruskan ke adapter (`GeminiProvider.generate`, `GroqProvider.generate`, `OpenRouterProvider.generate`).

---

## 2. Analisis Per Komponen (3 Pertanyaan Audit)

### 1. Apa yang sudah dilakukan / dioptimasi?
- **Intent Routing Sederhana**: Sudah ada `classify_intent()` yang memisahkan intent `chat`, `finance`, `network`, dan `full`. Jika pesan hanya bertema finance, tool network tidak dikirim (dan sebaliknya).
- **Escape Role Spoofing**: `AIReplyUseCase` sudah memiliki fungsi `_escape_role_spoof` untuk mencegah prompt injection dari history.
- **Character Budget Truncation (C6)**: Ada Truncation Guard `_truncate_to_char_budget` dengan batas `16.000` karakter.
- **Provider Fallback & Circuit Breaker**: Skema multi-provider yang robust untuk menangani rate-limit HTTP 429.

### 2. Ukuran Context Default yang Dikirim saat Ini
- **History Count**: `limit=20` pesan diambil dari DB untuk **semua** intent, termasuk sapaan kasual seperti "hallo".
- **Tool Definitions**:
  - Untuk `chat`: 0 tools (0 chars)
  - Untuk `finance`: 8 tools (~4.200 chars / ~1.050 token)
  - Untuk `network`: 8 tools (~3.500 chars / ~875 token)
  - Untuk `full`: 16 tools (~7.700 chars / ~1.925 token)
  - **Catatan**: Seluruh 8 tools finance selalu dikirim sekaligus walau user hanya bertanya "saldo BCA saya berapa?". Seluruh 8 tools network selalu dikirim walau user hanya bertanya "CPU MikroTik berapa?".
- **System Prompt**:
  - `chat`: ~565 chars (~140 token)
  - `finance`: ~1.450 chars (~360 token)
  - `network`: ~1.250 chars (~310 token)
  - `full`: ~2.100 chars (~520 token)

### 3. Titik-Titik Pemborosan Token Paling Jelas

1. **DB History Fetch Sebelum Intent Classification**:
   `AIReplyUseCase.execute` selalu melakukan fetch 20 pesan history dari DB **sebelum** intent diselidiki. Untuk pesan sapaan ("hallo", "hai"), 20 pesan history (~2.000-5.000 token) dikirim secara sia-sia.
2. **Tidak Ada Policy History per Intent (Static Limit = 20)**:
   Semua jenis query (termasuk query faktual sederhana seperti "saldo saya berapa?") membawa 20 pesan riwayat percakapan.
3. **Tidak Ada Fast-Path untuk Simple Chat / Greeting**:
   Pesan seperti "hallo", "terima kasih", "siapa kamu" tetap diproses lewat pipeline lengkap yang menyerap history 20 pesan.
4. **Semua Tools dalam Domain Dikirim Sekaligus (No Dynamic Sub-Tool Selection)**:
   Saat intent classified sebagai `finance`, **seluruh 8 tools finance** (termasuk `finance_create_account`, `finance_transfer`, `finance_get_monthly_report`, `finance_get_transactions`) ikut dikirim, padahal user hanya menanyakan saldo.
5. **Raw / Uncompacted Tool Result**:
   Hasil eksekusi tool (misalnya `mikrotik_get_logs` atau `finance_get_transactions` atau `mikrotik_get_health`) dikembalikan ke LLM dalam bentuk JSON mentah tanpa kompresi / summarization, berpotensi menghabiskan ribuan token pada turn kedua agentic loop.
6. **Agentic Loop Bertingkat Tanpa Structural Fast-Path untuk Mutations**:
   Untuk transaksi deterministik ("catat makan 25rb"), sistem melakukan 2 kali LLM call: LLM Call 1 (Tool Call) -> Tool Execution -> LLM Call 2 (Final text response confirmation). Padahal konfirmasi transaksi dapat diformat secara lokal dengan template response.
