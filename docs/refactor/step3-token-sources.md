# Step 3 — Identifikasi & Pemeringkatan Sumber Token

Dokumen ini mengidentifikasi dan mengurutkan sumber pemborosan token di sistem AI `whatsapp-assistant` dari yang paling mendasar/boros, serta memberikan estimasi kontribusi token per skenario sebagai **baseline sebelum refactoring**.

---

## 1. Pemeringkatan Sumber Pemborosan Token (Dari Paling Boros)

1. **Peringkat 1: Unfiltered History Fetch (Static 20 Messages)**
   - **Masalah**: Setiap pesan selalu menyertakan 20 pesan riwayat percakapan dari DB (~2.500–5.000 karakter / ~625–1.250 token), terlepas dari apakah pesan itu sapaan kasual ("hallo") atau pertanyaan sederhana.
   - **Kontribusi**: ~40% - 60% total token input pada single-turn chat & initial tool call.

2. **Peringkat 2: Double LLM Calls pada Tool Calling (Tanpa Fast-Path/Local Response)**
   - **Masalah**: Setiap kali tool dipanggil (query saldo, query CPU, catat pengeluaran), sistem selalu melakukan 2 kali LLM call. Call 2 mengulang **seluruh prompt dari Call 1** plus assistant tool request dan raw tool result.
   - **Kontribusi**: Melipatgandakan (2x) biaya input token per interaksi bernilai tool.

3. **Peringkat 3: All-Tools In-Domain Payload (Tanpa Sub-Tool Filtering)**
   - **Masalah**: Ketika intent terdeteksi `finance` atau `network`, seluruh 8 tools dalam domain tersebut dikirim sekaligus.
   - **Ukuran**:
     - 8 Finance Tools: ~4.200 karakter (~1.050 token)
     - 8 MikroTik Tools: ~3.500 karakter (~875 token)
     - 16 Full Tools: ~7.700 karakter (~1.925 token)

4. **Peringkat 4: System Prompt Ukuran Besar yang Digabung (Monolithic System Prompts)**
   - **Masalah**: Prompt `AI_FULL_SYSTEM_PROMPT` berukuran 2.100 karakter (~520 token), `AI_FINANCE_SYSTEM_PROMPT` 1.450 karakter (~360 token), `AI_NETWORK_SYSTEM_PROMPT` 1.250 karakter (~310 token). Banyak instruksi berulang yang bisa di-modularisasi.

5. **Peringkat 5: Raw / Uncompacted Tool Result Payload**
   - **Masalah**: Hasil eksekusi API MikroTik atau query DB Finance dikembalikan mentah ke LLM tanpa dikompresi, menyumbang ~300 - 2.000 karakter (~75–500 token) tambahan pada LLM Call 2.

---

## 2. Baseline Estimasi Konsumsi Token per Skenario (Existing Baseline)

*Asumsi: 1 token ≈ 4 karakter teks.*
*Rata-rata 20 pesan history = ~2.500 karakter (~625 token).*

### Skenario 1: `"hallo"`
- **Intent**: `chat` (1 LLM Call)
- **History Chars**: 2.500 chars (~625 tokens)
- **System Prompt Chars**: 565 chars (~141 tokens)
- **Tool Definitions Chars**: 0 chars (0 tokens)
- **Tool Result Chars**: 0 chars (0 tokens)
- **Total Input Tokens (1 Call)**: **~766 tokens**
- **Output Tokens**: ~30 tokens
- **Total Consumption**: **~796 tokens** *(Sangat boros untuk sekadar menyapa)*

---

### Skenario 2: `"kamu siapa?"`
- **Intent**: `chat` (1 LLM Call)
- **History Chars**: 2.500 chars (~625 tokens)
- **System Prompt Chars**: 565 chars (~141 tokens)
- **Tool Definitions Chars**: 0 chars (0 tokens)
- **Tool Result Chars**: 0 chars (0 tokens)
- **Total Input Tokens (1 Call)**: **~766 tokens**
- **Output Tokens**: ~40 tokens
- **Total Consumption**: **~806 tokens**

---

### Skenario 3: `"saldo BCA saya berapa?"`
- **Intent**: `finance` (2 LLM Calls)
- **Call 1 (Tool Request)**:
  - History: 2.500 chars (~625 tokens)
  - System Prompt: 1.450 chars (~362 tokens)
  - Tool Definitions (8 Finance Tools): 4.200 chars (~1.050 tokens)
  - Input Tokens Call 1: **~2.037 tokens**
- **Tool Result**: `finance_get_balance` output (~300 chars / ~75 tokens)
- **Call 2 (Final Response Synthesis)**:
  - Input Tokens Call 2: ~2.037 + ~25 (assistant call) + ~75 (tool result) = **~2.137 tokens**
- **Total Input Tokens**: **~4.174 tokens**
- **Output Tokens**: ~100 tokens
- **Total Consumption**: **~4.274 tokens**

---

### Skenario 4: `"CPU MikroTik saya berapa?"`
- **Intent**: `network` (2 LLM Calls)
- **Call 1 (Tool Request)**:
  - History: 2.500 chars (~625 tokens)
  - System Prompt: 1.250 chars (~312 tokens)
  - Tool Definitions (8 MikroTik Tools): 3.500 chars (~875 tokens)
  - Input Tokens Call 1: **~1.812 tokens**
- **Tool Result**: `mikrotik_get_health` output (~600 chars / ~150 tokens)
- **Call 2 (Final Response Synthesis)**:
  - Input Tokens Call 2: ~1.812 + ~25 + ~150 = **~1.987 tokens**
- **Total Input Tokens**: **~3.799 tokens**
- **Output Tokens**: ~120 tokens
- **Total Consumption**: **~3.919 tokens**

---

### Skenario 5: `"kondisi MikroTik saya gimana?"`
- **Intent**: `network` (2 LLM Calls)
- **Call 1 (Tool Request)**:
  - History: 2.500 chars (~625 tokens)
  - System Prompt: 1.250 chars (~312 tokens)
  - Tool Definitions (8 MikroTik Tools): 3.500 chars (~875 tokens)
  - Input Tokens Call 1: **~1.812 tokens**
- **Tool Result**: `mikrotik_get_health` + `mikrotik_get_traffic` (~1.500 chars / ~375 tokens)
- **Call 2 (Final Response Synthesis)**:
  - Input Tokens Call 2: ~1.812 + ~35 + ~375 = **~2.222 tokens**
- **Total Input Tokens**: **~4.034 tokens**
- **Output Tokens**: ~200 tokens
- **Total Consumption**: **~4.234 tokens**

---

## 3. Ringkasan Baseline

| Skenario | History Tokens | Tool Def Tokens | System Prompt Tokens | Tool Res Tokens | Total Input (Cumulative) | Output Tokens | Total Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `"hallo"` | 625 | 0 | 141 | 0 | **766** | 30 | **796** |
| `"kamu siapa?"` | 625 | 0 | 141 | 0 | **766** | 40 | **806** |
| `"saldo BCA saya berapa?"` | 1.250 (2x) | 2.100 (2x) | 724 (2x) | 75 | **4.174** | 100 | **4.274** |
| `"CPU MikroTik saya berapa?"` | 1.250 (2x) | 1.750 (2x) | 624 (2x) | 150 | **3.799** | 120 | **3.919** |
| `"kondisi MikroTik saya gimana?"` | 1.250 (2x) | 1.750 (2x) | 624 (2x) | 375 | **4.034** | 200 | **4.234** |
