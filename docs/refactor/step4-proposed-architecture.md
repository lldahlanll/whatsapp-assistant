# Step 4 — Proposed Architecture: Token Efficiency & Architectural Refactoring

Dokumen ini menyajikan rancangan arsitektur baru AI Pipeline yang teroptimasi secara token, memuat prinsip desain, pipeline per-step, modul yang akan dibuat/diubah, serta strategi kompatibilitas.

---

## 1. Pipeline Arsitektur Baru

```text
Inbound Message
      │
      ▼
┌─────────────┐
│ Pre-Router  │ ──► [Match Fast Greeting / Simple Chat?]
└──────┬──────┘     - "hallo", "hai", "terima kasih", "siapa kamu" (Strict Exact/Pattern Match)
       │            - YES ──► Intent = "simple_chat" (Skip Intent Classification & History Fetch)
       │ NO
       ▼
┌─────────────────────────┐
│ Intent Classification   │ ──► Rule-based Keyword Matching (classify_intent)
└──────────┬──────────────┘     Returns: "simple_chat" | "chat" | "finance" | "network" | "complex"
           │
           ▼
┌─────────────────────────┐
│     Context Policy      │ ──► Pusat kebijakan Context (Dataclass + Env Var Config)
└──────────┬──────────────┘     history_messages_limit:
           │                      - simple_chat = 0
           │                      - chat        = 3  (ENV: AI_CHAT_HISTORY_LIMIT)
           │                      - network     = 3  (ENV: AI_NETWORK_HISTORY_LIMIT)
           │                      - finance     = 5  (ENV: AI_FINANCE_HISTORY_LIMIT)
           │                      - complex     = 8  (ENV: AI_COMPLEX_HISTORY_LIMIT)
           ▼
┌─────────────────────────┐
│       Tool Policy       │ ──► Dynamic Tool Selector (Grouped per sub-domain)
└──────────┬──────────────┘     - simple_chat / chat => 0 tools
           │                    - finance_balance    => [finance_get_balance]
           │                    - finance_mutation   => [finance_add_expense, finance_add_income, finance_transfer]
           │                    - network_health     => [mikrotik_get_health, mikrotik_get_traffic]
           │                    - network_full       => [semua network tools]
           ▼
┌─────────────────────────┐
│     Context Builder     │ ──► Mengambil DB History SESUAI limit Context Policy
└──────────┬──────────────┘     Composes: Modular System Prompt (BASE + SPECIFIC) + History + User Msg
           │
           ▼
┌─────────────────────────┐
│     AIService (LLM)     │ ──► Provider Agnostic Call (Gemini, Groq, OpenRouter)
└──────────┬──────────────┘     + Token & LLM Metrics Observability Logger
           │
           ├─► Simple Chat / No Tools ───────────────► Final Text Response (1 Call)
           │
           └─► Tool Call Requested
                 │
                 ▼
           Tool Execution
                 │
                 ▼
           Compact Tool Result ──► Ringkas raw JSON / Truncate jika > MAX_TOOL_RESULT_CHARS
                 │
                 ▼
           LLM Final Response (Call 2, jika tidak diringkas oleh Application Layer Fast-Path)
```

---

## 2. Detail Modul & Komponen Utama

### A. Pre-Router & Intent Classification
- **Pre-Router**: Fast path untuk sapaan dan ucapan simpel yang tidak memerlukan tools maupun konteks percakapan lama.
  - Pattern: Exact match atau regex ketat untuk kata seperti `"hallo"`, `"halo"`, `"hai"`, `"hello"`, `"terima kasih"`, `"makasih"`, `"ping"`.
  - **Constraint Guard**: Jika pesan mengandung kata kunci bernilai finansial/jaringan (misal `"halo, saldo BCA saya berapa?"`), Pre-Router akan menolak dan meneruskan ke `classify_intent()`.
- **Intent Types**:
  - `simple_chat`: Sapaan super singkat.
  - `chat`: Percakapan umum / tanya jawab bot ("kamu siapa?").
  - `finance`: Transaksi / query keuangan.
  - `network`: Query status / troubleshoot MikroTik RouterOS.
  - `complex` / `full`: Pertanyaan campuran finance & network.

### B. Terpusat ContextPolicy (Dataclass + Config Env)
Membuat file baru [`src/whatsapp_platform/infrastructure/ai/context_policy.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/context_policy.py):

```python
@dataclass(frozen=True)
class ContextPolicy:
    intent: str
    history_limit: int
    system_prompt: str
    tools: list[ToolDefinition]

class ContextPolicyManager:
    @classmethod
    def get_policy(cls, intent: str, settings: Settings) -> ContextPolicy:
        # Menentukan history limit & system prompt & tools berdasarkan intent
        ...
```
Configurable via environment variables (Settings):
- `AI_CHAT_HISTORY_LIMIT` (default 3)
- `AI_FINANCE_HISTORY_LIMIT` (default 5)
- `AI_NETWORK_HISTORY_LIMIT` (default 3)
- `AI_COMPLEX_HISTORY_LIMIT` (default 8)

### C. ToolPolicy & Sub-Domain Tool Grouping
Membuat modul [`src/whatsapp_platform/infrastructure/ai/tool_policy.py`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/tool_policy.py):
- **Finance Sub-Groups**:
  - `balance`: `finance_get_balance`
  - `transaction`: `finance_add_income`, `finance_add_expense`, `finance_transfer`, `finance_get_transactions`
  - `report`: `finance_get_monthly_report`, `finance_get_expense_summary`, `finance_get_balance`
  - `account`: `finance_create_account`, `finance_get_balance`
- **Network Sub-Groups**:
  - `system_resource`: `mikrotik_get_health`
  - `traffic_interface`: `mikrotik_get_traffic`
  - `dhcp_clients`: `mikrotik_get_dhcp_leases`
  - `diagnostics`: `mikrotik_get_health`, `mikrotik_get_traffic`, `mikrotik_get_logs`, `mikrotik_get_connections`

### D. Modular System Prompts (Modular Assembly)
Memecah prompt raksasa di `constants.py` menjadi komponen modular:
- `BASE_SYSTEM_PROMPT`: Aturan umum bahasa, kesopanan, keamanan, WhatsApp formatting (~300 chars / ~75 tokens).
- `CHAT_SYSTEM_PROMPT`: Identitas Nara sebagai AI assistant (~150 chars).
- `FINANCE_SYSTEM_PROMPT`: Panduan pencatatan uang & format Rupiah (~400 chars).
- `NETWORK_SYSTEM_PROMPT`: Panduan analisis RouterOS & sintesis jaringan (~350 chars).

### E. Compact Tool Result & Dynamic Limits (P1)
- Setiap hasil tool eksekusi diproses oleh `CompactToolResultFormatter`.
- Mengkonversi JSON response berukuran besar (seperti log 30 baris atau 50 DHCP lease) menjadi ringkasan terstruktur.
- `MAX_TOOL_RESULT_CHARS` (default 1.000 chars) dipasang untuk mencegah kelebihan token.

### F. Observability Logging (`AI_METRICS`)
Mencatat log terstruktur `AI_METRICS` tanpa mencatat isi pesan sensitif:
- `request_id`, `chat_jid`, `intent`, `model`, `provider`, `history_message_count`, `history_chars`, `system_prompt_chars`, `tool_count`, `tool_definition_chars`, `tool_result_chars`, `input_tokens`, `output_tokens`, `total_tokens`, `llm_call_number`, `total_llm_calls`, `latency_ms`.

---

## 3. Rencana Perubahan File (File Modification Plan)

### File Baru yang Akan Dibuat
1. `src/whatsapp_platform/infrastructure/ai/context_policy.py`: Definisi `ContextPolicy` dataclass & `ContextPolicyManager`.
2. `src/whatsapp_platform/infrastructure/ai/tool_policy.py`: Grouping tools per intent & sub-intent keyword analyzer.
3. `src/whatsapp_platform/infrastructure/ai/pre_router.py`: Pre-router fast path untuk `simple_chat`.
4. `src/whatsapp_platform/infrastructure/ai/compact_formatter.py`: Compaction & summarizer untuk tool results.
5. `src/whatsapp_platform/infrastructure/ai/metrics_logger.py`: Token & LLM call observability logging.

### File Existing yang Akan Diubah
1. `src/whatsapp_platform/infrastructure/config/settings.py`: Menambahkan env variables untuk history limit per intent & tool result limit.
2. `src/whatsapp_platform/infrastructure/ai/constants.py`: Refactoring `classify_intent`, meremajakan keyword list, dan memecah system prompt menjadi modular.
3. `src/whatsapp_platform/application/use_cases/ai_reply.py`: Mengubah alur: Intent & Pre-Router -> Fetch History -> Dynamic Tool & Prompt Assembly -> AIService call.
4. `src/whatsapp_platform/infrastructure/ai/ai_service.py`: Mengintegrasikan observability logger, tool result compacting, dan max tool iteration limit.
5. `src/whatsapp_platform/container.py`: Wiring dependency baru ke container.

---

## 4. Rencana Tahap Eksekusi (Implementation Phasing)

- **Step 5 (P0 - Critical)**:
  - Implementasi Pre-Router + Intent classification SEBELUM history fetch.
  - Implementasi `ContextPolicy` dataclass & Env configuration.
  - Dynamic tool selection berdasarkan intent.
  - `AI_METRICS` Observability logging per request.
- **Step 6**: Test Suite P0 + Verifikasi log `AI_METRICS`.
- **Step 7 (P1 - Advanced Optimization)**:
  - Compact tool result formatter (`MAX_TOOL_RESULT_CHARS`).
  - Structured extraction fast-path untuk mutasi keuangan.
  - Network & Finance Sub-domain Tool Grouping.
  - Enforcement MAX_TOOL_ITERATIONS.
- **Step 8**: Test Suite P1 + Verifikasi log.
- **Step 9**: Benchmark BEFORE vs AFTER (Pengukuran Asli).
- **Step 10**: Final Report.
