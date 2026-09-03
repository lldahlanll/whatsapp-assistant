# Step 2 — Arsitektur Existing AI Pipeline

Dokumen ini menguraikan alur kerja (sequence flow) arsitektur AI yang berjalan saat ini pada `whatsapp-assistant`, berdasarkan audit di Step 1.

---

## 1. Flow Diagram Arsitektur Existing (Pesan Masuk → Reply Keluar)

```text
 Inbound WhatsApp Message (MessageReceived Event)
                       │
                       ▼
            ┌─────────────────────┐
            │  AIMessageHandler   │
            └──────────┬──────────┘
                       │ Validasi Guards (Idempotency, Self, Non-Text, Prefix '!',
                       │                  Phone core extractor, Config enabled,
                       │                  Group mention/reply, Rate guard)
                       ▼
            ┌─────────────────────┐
            │  AIReplyUseCase     │
            └──────────┬──────────┘
                       │
                       ├──────► [STEP A] Fetch History dari DB (GetConversationHistoryUseCase)
                       │                 - Selalu fetch LIMIT = 20 pesan
                       │                 - Truncate jika > 16.000 chars
                       │
                       ├──────► [STEP B] Classify Intent (classify_intent)
                       │                 - Menggunakan keyword matching pada trigger message
                       │                 - Returns: "chat" | "finance" | "network" | "full"
                       │
                       ├──────► [STEP C] Select System Prompt & Tool Set
                       │                 - chat    => AI_SYSTEM_PROMPT + No tools
                       │                 - finance => AI_FINANCE_SYSTEM_PROMPT + 8 Finance Tools
                       │                 - network => AI_NETWORK_SYSTEM_PROMPT + 8 MikroTik Tools
                       │                 - full    => AI_FULL_SYSTEM_PROMPT    + 16 Tools
                       │
                       ▼
            ┌─────────────────────┐
            │     AIService       │
            └──────────┬──────────┘
                       │
                       ├───► Scenario A: No Tools ("chat" intent)
                       │     │
                       │     ▼
                       │   LLM Call 1 (Single Pass) ──► Return Text Response
                       │
                       └───► Scenario B: With Tools ("finance" / "network" / "full")
                             │
                             ▼
                           LLM Call 1 (With Tools Payload)
                             │
                             ├─► [No Tool Call Requested] ──► Return Text Response
                             │
                             └─► [Tool Calls Requested]
                                   │
                                   ▼
                             CompositeToolExecutor
                                   │ (Jalankan Tool MikroTik / Finance)
                                   ▼
                             Raw Tool Result (Uncompacted JSON string)
                                   │
                                   ▼
                             Append to Conversation (role: "assistant", role: "tool")
                                   │
                                   ▼
                             LLM Call 2 (Agentic Loop Iteration)
                                   │
                                   ▼
                             Return Final Text Response
                                   │
                       ┌──────────┴──────────┐
                       ▼                     ▼
             Append to Context      Send Message to User
                (SQLite Cache)        (SendMessageUseCase)
```

---

## 2. Analisis Detail Alur Existing

### 1. Kapan History Diambil Relatif Terhadap Intent Classification?
- **Urutan saat ini**: History diambil **LEBIH DULU** sebelum Intent Classification.
- **Lokasi Code**: [`AIReplyUseCase.execute()`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/application/use_cases/ai_reply.py#L140-L155)
  - Line 140: `history = await self._get_conv_uc.execute(chat_jid_str, limit=20)`
  - Line 146: `history = self._truncate_to_char_budget(history, chat_jid_str)`
  - Line 155: `intent = classify_intent(trigger_text)`
- **Dampak Token**: Bahkan untuk pesan sapaan seperti `"hallo"`, query DB tetap menarik 20 pesan history terakhir dan memasukkannya ke dalam list message yang dikirim ke LLM.

### 2. Kapan dan Bagaimana Tools Dipilih?
- **Filtering Domain**: Ada filtering tingkat **domain** (Finance vs Network vs Chat).
  - Jika intent `"chat"`, 0 tools dikirim.
  - Jika intent `"finance"`, **semua 8 tools finance** dikirim (total ~4.200 karakter schema).
  - Jika intent `"network"`, **semua 8 tools MikroTik** dikirim (total ~3.500 karakter schema).
  - Jika intent `"full"`, **semua 16 tools** dikirim (total ~7.700 karakter schema).
- **Keterbatasan**: Tidak ada sub-tool filtering. Misalnya jika pesan user adalah `"saldo BCA saya berapa?"`, 7 tools finance lainnya (termasuk `finance_create_account`, `finance_transfer`, `finance_add_expense`, dll.) tetap dikirim ke LLM.

### 3. Berapa Kali LLM Dipanggil Berdasarkan Skenario?

| Skenario | Intent | Jumlah LLM Call | Alur Panggilan |
| :--- | :--- | :---: | :--- |
| **Chat biasa** ("hallo", "kamu siapa?") | `chat` | **1 Call** | LLM (Text response) |
| **Network query** ("CPU MikroTik saya berapa?") | `network` | **2 Calls** | Call 1: Request `mikrotik_get_health` <br> Call 2: Synthesize text response |
| **Finance query** ("saldo BCA saya berapa?") | `finance` | **2 Calls** | Call 1: Request `finance_get_balance` <br> Call 2: Synthesize text response |
| **Finance mutation** ("catat makan 25rb") | `finance` | **2 Calls** | Call 1: Request `finance_add_expense` <br> Call 2: Synthesize text response |

### 4. Di Mana & Bagaimana Tool Result Diproses Sebelum Dikirim Balik ke LLM?
- **Lokasi Code**: [`AIService.generate_reply_with_tools()`](file:///Users/ephinu/Project/whatsapp-assistant/src/whatsapp_platform/infrastructure/ai/ai_service.py#L375-L388)
- **Kondisi Data**: Tool output dikembalikan dari `CompositeToolExecutor` sebagai **JSON string mentah** (raw string dump).
- **Pengolahan**: `ProviderMessage(role="tool", content=tool_output)` langsung di-append ke array pesan tanpa kompresi, tanpa filtering key penting, dan tanpa batas `MAX_TOOL_RESULT_CHARS`.
