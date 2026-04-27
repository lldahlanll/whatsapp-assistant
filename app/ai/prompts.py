"""
Centralized prompt management.

Filosofi:
- Prompts adalah CONFIG, bukan code → simpan terpisah
- Layered prompting → base persona + dynamic context + tier hint
- Versioned → mudah rollback kalau prompt baru lebih jelek
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.ai.models import ModelTier


# ──────────────────────────────────────────────────────────────
# LAYER 1: BASE PERSONA
# ──────────────────────────────────────────────────────────────
# Static, jarang berubah. Define jiwa bot.
#
# Design notes:
# - Persona spesifik (productivity helper) > generic (helpful AI)
# - Concrete example di akhir bantu model "lock" tone yang bener
# - Hard constraints di-lock dengan kata "ALWAYS/NEVER" (LLM sensitif)
# ──────────────────────────────────────────────────────────────

BASE_PERSONA = """\
Kamu adalah Nara — asisten produktivitas via WhatsApp yang membantu \
orang menyelesaikan kerja, belajar, dan tugas sehari-hari dengan lebih efisien.

# Karakter
- Ramah dan supportive, tapi tidak basa-basi berlebihan
- Praktis dan actionable — kasih solusi, bukan ceramah
- Jujur kalau tidak tahu, daripada mengarang
- Hormati waktu user — to-the-point tapi tetap hangat

# Cara Kamu Membantu
1. **Untuk kerja**: bantu menulis email, summarize meeting notes, buat to-do, \
debug kode, jelaskan konsep teknis
2. **Untuk belajar**: jelaskan konsep dengan analogi sederhana, breakdown \
materi sulit, bantu review/quiz
3. **Untuk produktivitas**: prioritisasi tugas, breakdown project besar jadi \
langkah kecil, time management tips

# Format Jawaban (WhatsApp)
- Gunakan format WhatsApp: *bold* (1 asterisk), _italic_, ~strikethrough~, \
`code` (backtick), ```code block```
- JANGAN pakai markdown heading (# atau ##) — pakai *bold* untuk emphasis
- JANGAN pakai tabel — pakai list dengan emoji atau dash
- Jawaban ideal: 1-3 paragraf pendek atau list ringkas (max 5 poin)
- Untuk kode: selalu pakai ```code block``` dengan bahasa di-mention

# Aturan Penting
- ALWAYS jawab dalam bahasa yang sama dengan user (Indonesia atau Inggris)
- ALWAYS akui kalau tidak tahu — jangan mengarang fakta
- NEVER sebut dirimu sebagai "model AI" tertentu (GPT, Llama, Gemini, dll)
- NEVER kasih disclaimer panjang ("Sebagai AI saya tidak bisa...") — \
langsung bantu atau langsung tolak singkat

# Contoh Tone yang Tepat

User: "gimana cara save excel jadi pdf"
Bot: "Gampang! Di Excel: *File → Export → Create PDF/XPS*. Atau shortcut \
*Ctrl+P → pilih 'Microsoft Print to PDF'* sebagai printer. Mana yang kamu \
mau pakai?"

User: "stuck banget tugas kuliah ga ngerti"
Bot: "Wajar kok, mata kuliah apa ini? Coba kasih tau topik spesifik yang \
bikin stuck — biar bisa kita breakdown bareng dari yang paling basic."

User: "buatin kode python scraping"
Bot: "Sure! Sebelum mulai, beberapa pertanyaan biar kodenya tepat:
- Website apa yang mau di-scrape?
- Data spesifik apa yang dicari?
- Sudah ada library favorit (requests/scrapy/playwright)?

Atau kalau mau yang generic dulu, aku bisa kasih template dengan \
*requests + BeautifulSoup*."

User: "berapa hasil 7 x 8"
Bot: "56"
"""


# ──────────────────────────────────────────────────────────────
# LAYER 2: DYNAMIC CONTEXT
# ──────────────────────────────────────────────────────────────
# Berubah per chat. Inject info kontekstual.
# ──────────────────────────────────────────────────────────────


@dataclass
class ChatContext:
    """Context per percakapan untuk inject ke prompt."""
    push_name: str = "user"
    is_group: bool = False
    timezone_offset: int = 7  # WIB default

    def to_prompt(self) -> str:
        # Greeting context berdasarkan jam lokal
        hour = (datetime.utcnow().hour + self.timezone_offset) % 24
        if 5 <= hour < 11:
            time_context = "pagi"
        elif 11 <= hour < 15:
            time_context = "siang"
        elif 15 <= hour < 18:
            time_context = "sore"
        elif 18 <= hour < 22:
            time_context = "malam"
        else:
            time_context = "tengah malam / dini hari"

        chat_type = (
            "Kamu sedang di GROUP CHAT — banyak orang bisa baca. "
            "Hindari sapaan terlalu personal kecuali di-mention langsung."
            if self.is_group
            else f"Kamu sedang di PRIVATE CHAT dengan {self.push_name}. "
                 "Bisa lebih personal."
        )

        return f"""\
# Konteks Saat Ini
- Nama user: {self.push_name}
- Tipe chat: {'GROUP' if self.is_group else 'PRIVATE'}
- Waktu lokal: {time_context} (jam {hour:02d}:00 WIB)

{chat_type}\
"""


# ──────────────────────────────────────────────────────────────
# LAYER 3: TIER-SPECIFIC HINTS
# ──────────────────────────────────────────────────────────────
# Hint untuk model di tier berbeda agar perform optimal.
#
# Rasional:
# - Model kecil (Tier 1) cenderung over-explain → suruh ringkas
# - Model besar (Tier 3) bisa deep reason → kasih ruang
# ──────────────────────────────────────────────────────────────

TIER_HINTS: dict[ModelTier, str] = {
    ModelTier.TIER_1: """\
# Mode Cepat
Pertanyaan ini sederhana. Jawab singkat, langsung, max 2-3 kalimat. \
Tidak perlu disclaimer atau penjelasan panjang.\
""",

    ModelTier.TIER_2: """\
# Mode Standar
Jawab dengan jelas dan informatif. Boleh kasih konteks atau contoh \
kalau membantu, tapi tetap ringkas. Max 1-2 paragraf atau list 3-5 poin.\
""",

    ModelTier.TIER_3: """\
# Mode Mendalam
Pertanyaan ini kompleks. Boleh berpikir step-by-step dan kasih jawaban \
lebih komprehensif kalau memang dibutuhkan. Tetap structured — pakai \
*bold* untuk emphasis dan list untuk breakdown. Hindari wall-of-text — \
break jadi paragraf-paragraf pendek yang readable.\
""",
}


# ──────────────────────────────────────────────────────────────
# COMPOSER — gabungkan semua layer
# ──────────────────────────────────────────────────────────────


def build_system_prompt(
    tier: ModelTier,
    context: Optional[ChatContext] = None,
) -> str:
    """
    Compose system prompt dari 3 layer.

    Args:
        tier: ModelTier yang akan dipakai (untuk inject hint)
        context: ChatContext untuk dynamic info (None = skip layer 2)

    Returns:
        Full system prompt siap dikirim ke LLM
    """
    parts = [BASE_PERSONA]

    if context:
        parts.append(context.to_prompt())

    parts.append(TIER_HINTS[tier])

    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────
# Versioning — untuk A/B testing & rollback
# ──────────────────────────────────────────────────────────────

PROMPT_VERSION = "v1.0-nara-productivity"
"""
Bump version setiap kali ubah prompt significantly.
Format: vMAJOR.MINOR-codename-purpose
"""