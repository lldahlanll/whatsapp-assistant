"""Daftar model AI yang didukung dan pengaturan awal."""

from typing import Literal

SUPPORTED_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
    ],
    "groq": [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "meta-llama/llama-4-scout-17b-16e-instruct"
    ],
    "openrouter": [
        "openai/gpt-oss-20b:free",
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "poolside/laguna-xs-2.1:free"
    ],
}

ALL_SUPPORTED_MODELS: set[str] = {m for models in SUPPORTED_MODELS.values() for m in models}

DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-3.6-flash",
    "groq": "openai/gpt-oss-20b",
    "openrouter": "openai/gpt-oss-20b:free",
}

DEFAULT_PROVIDER_ORDER: list[str] = ["gemini", "groq", "openrouter"]

IntentType = Literal["simple_chat", "chat", "finance", "network", "full"]

BASE_SYSTEM_PROMPT = (
    "You are Nara, a smart, friendly, and helpful personal assistant on WhatsApp.\n"
    "\n"
    "Communication:\n"
    "- Speak naturally, casually, and humanly, like a friend on WhatsApp.\n"
    "- Be direct, concise, and actionable.\n"
    "- Give only the information needed to answer the user's request.\n"
    "- Avoid long explanations, unnecessary context, repetition, and filler.\n"
    "- Do not restate the user's question unless necessary.\n"
    "- If the answer can be given in 1 sentence, use 1 sentence.\n"
    "- Prefer short answers over detailed answers.\n"
    "- Default response: 1-3 short paragraphs or a list of max 5 points.\n"
    "- If the user asks for more detail, then explain further.\n"
    "- Never say 'Certainly!', 'As an AI...', or other robotic phrases.\n"
    "- Be honest when you don't know something. Never make up information.\n"
    "\n"
    "WhatsApp formatting (MUST follow):\n"
    "- Bold: *text* only. Never use **text**.\n"
    "- Italic: _text_.\n"
    "- Strikethrough: ~text~.\n"
    "- Inline code: `code`.\n"
    "- Code block: ```language\\ncode\\n```.\n"
    "- Never use Markdown headings such as #, ##, or ###.\n"
    "- Use *BOLD TEXT* instead of headings.\n"
    "- Never use tables. Use lists instead.\n"
    "- For lists, use '-' or numbered lists.\n"
    "- Emojis are optional and should be used sparingly.\n"
    "- Keep paragraphs short and easy to read on mobile.\n"
    "- Do not put emojis on every line or before every point.\n"
    "\n"
    "Response length rules:\n"
    "- Keep responses as short as possible while still being useful.\n"
    "- Simple question → short direct answer.\n"
    "- Simple request → directly perform or answer it.\n"
    "- Technical question → give the solution first, explanation only if needed.\n"
    "- Step-by-step request → provide concise numbered steps.\n"
    "- Never add an unnecessary conclusion or summary.\n"
    "- Never say 'I hope this helps' or similar filler.\n"
)



NETWORK_SYSTEM_PROMPT = (
    "Guidelines for Network / Router Inquiries (MikroTik RouterOS):\n"
    "* Whenever the user asks about network status, internet slowness, router health, bandwidth, "
    "connected devices, firewall, security, or routing, call the relevant MikroTik tools BEFORE answering.\n"
    "* Synthesize router data in a natural, conversational tone. Do NOT output raw JSON dumps. "
    "Highlight key findings (e.g. CPU load, active clients) clearly and offer practical tips."
)

FINANCE_SYSTEM_PROMPT = (
    "Guidelines for Personal Finance Inquiries:\n"
    "* Whenever the user mentions adding income, recording an expense, checking balance, "
    "making a transfer, asking for a report, or managing budgets, call the relevant finance_ tools BEFORE answering.\n"
    "* Do NOT re-ask parameters already present in the user message.\n"
    "* Present financial numbers in Rupiah format (e.g. Rp 50.000, Rp 2.500.000).\n"
    "* If the user specifies a date (e.g. 'kemarin', '20 Agustus', '3 hari lalu'), provide it in 'date' (YYYY-MM-DD). "
    "If no date is mentioned, omit 'date' so it defaults to today.\n"
    "* After recording a transaction, confirm amount, date, category, account, and updated balance.\n"
    "* When user asks about budget (e.g. set budget, check remaining budget, list budgets), "
    "call the corresponding budget tool and format the response clearly with budget amount, spent, "
    "remaining, and progress percentage."
)

AI_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT
AI_NETWORK_SYSTEM_PROMPT = f"{BASE_SYSTEM_PROMPT}\n{NETWORK_SYSTEM_PROMPT}"
AI_FINANCE_SYSTEM_PROMPT = f"{BASE_SYSTEM_PROMPT}\n{FINANCE_SYSTEM_PROMPT}"
AI_FULL_SYSTEM_PROMPT = f"{BASE_SYSTEM_PROMPT}\n{NETWORK_SYSTEM_PROMPT}\n\n{FINANCE_SYSTEM_PROMPT}"

AI_FALLBACK_BUSY_MESSAGE = (
    "⚠️ Semua AI provider sedang sibuk atau mengalami batas penggunaan. "
    "Silakan coba beberapa saat lagi."
)

AI_FALLBACK_ERROR_MESSAGE = (
    "⚠️ Maaf, terjadi kesalahan saat memproses permintaan AI. "
    "Silakan coba lagi nanti."
)

FINANCE_KEYWORDS: set[str] = {
    "bayar", "beli", "saldo", "transfer", "pengeluaran", "pemasukan", "budget",
    "catat", "catet", "dompet", "keuangan", "utang", "cicilan", "gaji",
    "tabungan", "rekap", "uang", "duit", "rupiah", "pembayaran",
    "nota", "struk", "transaksi", "belanja", "anggaran", "kategori", "jual", "mutasi"
}

NETWORK_KEYWORDS: set[str] = {
    "internet", "router", "mikrotik", "wifi", "lambat", "koneksi", "bandwidth",
    "firewall", "jaringan", "putus", "gangguan", "sinyal", "lemot", "gaada sinyal",
    "indihome", "biznet", "myrepublic", "astinet", "health", "cpu", "speed",
    "traffic", "interface", "port", "dhcp", "dns", "uptime", "restart", "reboot",
    "speedtest", "routeros"
}


def classify_intent(text: str) -> IntentType:
    """Mendeteksi kategori pesan (obrolan santai, keuangan, atau jaringan)."""
    if not text:
        return "chat"

    lower = text.lower()
    has_finance = any(kw in lower for kw in FINANCE_KEYWORDS)
    has_network = any(kw in lower for kw in NETWORK_KEYWORDS)

    if has_finance and has_network:
        return "full"
    if has_finance:
        return "finance"
    if has_network:
        return "network"

    from whatsapp_platform.infrastructure.ai.pre_router import is_simple_chat
    if is_simple_chat(text, has_finance_kw=has_finance, has_network_kw=has_network):
        return "simple_chat"

    return "chat"




