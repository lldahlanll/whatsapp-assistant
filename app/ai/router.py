import re
from loguru import logger
from app.ai.client import openrouter_client
from app.ai.models import ModelTier, get_model, get_fallback_chain

# ── Classifier Rules ──────────────────────────────────────────
#
# Sistem klasifikasi berbasis rule (cepat, tidak butuh API call tambahan).
# Urutan pengecekan: TIER_3 dulu (paling ketat), baru TIER_1 (paling longgar).
#

# Kata kunci teknikal → Tier 3
TIER3_KEYWORDS = [
    # Programming
    "code", "kode", "program", "debug", "error", "function", "class",
    "algorithm", "algoritma", "database", "query", "sql", "api",
    "docker", "server", "deploy", "python", "javascript", "json",
    # Analisis kompleks
    "analisis", "analysis", "explain", "jelaskan", "bandingkan",
    "compare", "perbedaan", "difference", "bagaimana cara", "how to",
    "implementasi", "implement", "arsitektur", "architecture",
    # Penulisan panjang
    "essay", "artikel", "laporan", "report", "summary", "rangkuman",
    "translate", "terjemahkan", "revisi", "review",
]

# Indikator pesan panjang/kompleks → Tier 2
TIER2_KEYWORDS = [
    "kenapa", "mengapa", "why", "apa itu", "what is", "cerita",
    "story", "tolong bantu", "please help", "bisa jelaskan",
    "rekomendasikan", "recommend", "saran", "advice", "pendapat",
    "opinion", "pikir", "think", "rencana", "plan",
]

def classify_message(text: str) -> ModelTier:
    """
    Klasifikasi pesan ke ModelTier berdasarkan konten & panjang.

    Logika:
    1. Pesan panjang (>200 karakter) → minimal Tier 2
    2. Ada keyword teknikal → Tier 3
    3. Ada keyword medium → Tier 2
    4. Default → Tier 1

    Args:
        text: Teks pesan dari user

    Returns:
        ModelTier yang sesuai
    """
    text_lower = text.lower().strip()
    char_count = len(text_lower)
    word_count = len(text_lower.split())

    logger.debug(
        f"[Classier] Input: {char_count} chars, {word_count} words | "
        f"Preview: {text[:80]}..."
    )

    # ── Rule 1: Keyword Tier 3 (teknikal/kompleks) ────────────
    for keyword in TIER3_KEYWORDS:
        if keyword in text_lower:
            logger.info(f"[Classifier] -> TIER_3 (keyword: '{keyword}')")
            return ModelTier.TIER_3

    # ── Rule 2: Pesan sangat panjang (>500 char) → Tier 3 ────
    if char_count > 500:
        logger.info(f"[Classifier] -> TIER_3 (very long: {char_count} chars)")
        return ModelTier.TIER_3
    
    # ── Rule 3: Keyword Tier 2 ────────────────────────────────
    for keyword in TIER2_KEYWORDS:
        if keyword in text_lower:
            logger.info(f"[Classfier] -> TIER_2 (keyword: '{keyword}')")
            return ModelTier.TIER_2

    # ── Rule 4: Pesan medium (>200 char) → Tier 2 ────────────
    if char_count > 200:
        logger.info(f"[Classfier] -> TIER_2 (mediun length: {char_count} chars)")
        return ModelTier.TIER_2

    # ── Default: Tier 1 ───────────────────────────────────────
    logger.info(f"[Classfier] -> TIER_1 (default, short message)")
    return ModelTier.TIER_1


async def route_and_generate(
    messages: list[dict],
    user_text: str,
) -> tuple[str, str]:
    """
    Classify pesan → pilih model → generate response dengan fallback.

    Args:
        messages  : Full conversation history dalam format OpenAI chat
        user_text : Teks pesan terbaru dari user (untuk classifier)

    Returns:
        Tuple (response_text, model_name_used)
        response_text = "" jika semua model gagal
    """
    # 1. Classify
    tier = classify_message(user_text)
    fallback_chain = get_fallback_chain(tier)

    logger.info(
        f"[Router] Starting chain: "
        f"{'->'.join(m.name for m in fallback_chain)}"
    )

    # 2. Coba setiap model dalam chain
    for model in fallback_chain:
        logger.info(f"[Router] Trying: {model.name} ({model.model_id})")

        response = await openrouter_client.chat(
            model_id=model.model_id,
            messages=messages,
            max_tokens=model.max_tokens,
        )

        if response:
            logger.info(f"[Router] ✓ Success with: {model.name}")
            return response, model.name
        
        logger.warning(f"[Router] ✗ Failed: {model.name}, trying next...")


    # 3. Semua model gagal
    logger.error("[Router] All models in fallback chain failed!")
    return "", "none"
