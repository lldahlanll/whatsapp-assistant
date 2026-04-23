from enum import Enum
from dataclasses import dataclass

class ModelTier(Enum):
    """
    Tier menentukan kapan model ini dipilih oleh classifier.
    
    TIER_1 → pesan simple/pendek (hemat resource)
    TIER_2 → pesan medium/butuh reasoning
    TIER_3 → pesan kompleks/teknikal/panjang
    """
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3

@dataclass
class AIModel:
    """Representasi satu model AI."""
    name: str           # Nama display
    model_id: str       # ID untuk OpenRouter API
    tier: ModelTier     # Tier routing
    max_tokens: int     # Batas output token
    description: str    # Deskripsi singkat

# ── Definisi 3 Model ──────────────────────────────────────────

MODELS = {
    ModelTier.TIER_1: AIModel(
        name="Trinity Large",
        model_id="arcee-ai/trinity-large-preview:free",
        tier=ModelTier.TIER_1,
        max_tokens=1024,
        description="Fast model untuk pesan pendek & casual",
    ),
    ModelTier.TIER_2: AIModel(
        name="GPT OSS 120B",
        model_id="openai/gpt-oss-120b:free",
        tier=ModelTier.TIER_2,
        max_tokens=2048,
        description="Model medium untuk reasoning & percakapan normal",
    ),
    ModelTier.TIER_3: AIModel(
        name="Nemotron Super 120B",
        model_id="nvidia/nemotron-3-super-120b-a12b:free",
        tier=ModelTier.TIER_3,
        max_tokens=4096,
        description="Model besar untuk tugas kompleks & teknikal",
    ),
}

# Urutan fallback: kalau Tier N gagal, coba Tier berikutnya
FALLBACK_ORDER = [
    ModelTier.TIER_1,
    ModelTier.TIER_2,
    ModelTier.TIER_3,
]

def get_model(tier: ModelTier) -> AIModel:
    return MODELS[tier]

def get_fallback_chain(start_tier: ModelTier) -> list[AIModel]:
    """
    Return urutan model untuk fallback dimulai dari tier tertentu.
    
    Contoh: start_tier=TIER_2 → [TIER_2, TIER_3, TIER_1]
    Setelah tier tertinggi, fallback ke tier terendah.
    """
    order = FALLBACK_ORDER
    start_idx = order.index(start_tier)
    
    # Mulai dari tier yang dipilih, lanjut ke atas, lalu ke bawah
    chain = order[start_idx:] + order[:start_idx]
    return [MODELS[tier] for tier in chain]