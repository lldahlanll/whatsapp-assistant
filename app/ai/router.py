# app/ai/router.py
import re
from typing import Optional

from loguru import logger

from app.ai.client import multi_client
from app.ai.models import ModelTier, get_fallback_routes
from app.ai.prompts import ChatContext, build_system_prompt

# ── Keywords (sama seperti sebelumnya) ────────────────────────
TIER3_KEYWORDS = [
    "code", "kode", "program", "debug", "error", "function", "class",
    "algorithm", "algoritma", "database", "query", "sql", "api",
    "docker", "server", "deploy", "python", "javascript", "json",
    "analisis", "analysis", "explain", "jelaskan", "bandingkan",
    "compare", "perbedaan", "difference", "implementasi", "implement",
    "arsitektur", "architecture", "essay", "artikel", "laporan",
    "report", "summary", "rangkuman", "translate", "terjemahkan",
    "revisi", "review",
]

TIER2_KEYWORDS = [
    "kenapa", "mengapa", "why", "cerita", "story", "rekomendasikan",
    "recommend", "saran", "advice", "pendapat", "opinion", "rencana",
    "plan",
]

_TIER3_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in TIER3_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_TIER2_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in TIER2_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def classify_message(text: str) -> ModelTier:
    text_clean = text.strip()
    char_count = len(text_clean)

    if match := _TIER3_PATTERN.search(text_clean):
        logger.info(f"[Classifier] → TIER_3 (keyword: '{match.group(1)}')")
        return ModelTier.TIER_3

    if char_count > 500:
        logger.info(f"[Classifier] → TIER_3 (long: {char_count} chars)")
        return ModelTier.TIER_3

    if match := _TIER2_PATTERN.search(text_clean):
        logger.info(f"[Classifier] → TIER_2 (keyword: '{match.group(1)}')")
        return ModelTier.TIER_2

    if char_count > 200:
        logger.info(f"[Classifier] → TIER_2 (medium: {char_count} chars)")
        return ModelTier.TIER_2

    logger.info(f"[Classifier] → TIER_1 (short: {char_count} chars)")
    return ModelTier.TIER_1


async def route_and_generate(
    history: list[dict],
    user_text: str,
    context: Optional[ChatContext] = None,
) -> tuple[str, str]:
    """
    Classify → build prompt → fallback chain via multi-provider.

    Args:
        history: User-assistant history dari memory (TANPA system prompt)
        user_text: Pesan user terbaru (untuk classifier)
        context: ChatContext untuk inject info kontekstual

    Returns:
        (response_text, route_name). response="" kalau semua gagal.
    """
    # 1. Classify
    tier = classify_message(user_text)

    # 2. Build layered system prompt
    system_prompt = build_system_prompt(tier=tier, context=context)

    # 3. Assemble final messages: system + history
    messages = [{"role": "system", "content": system_prompt}] + history

    # 4. Get fallback routes
    routes = get_fallback_routes(tier)
    if not routes:
        logger.error("[Router] No routes available for tier")
        return "", "none"

    logger.info(
        f"[Router] Tier {tier.name} | {len(routes)} routes | "
        f"prompt: {len(system_prompt)} chars | "
        f"history: {len(history)} msgs"
    )

    # 5. Try fallback chain
    for i, route in enumerate(routes, 1):
        logger.info(
            f"[Router] [{i}/{len(routes)}] Trying {route.name} "
            f"({route.endpoint_name}/{route.model_id})"
        )

        response = await multi_client.call(
            endpoint_name=route.endpoint_name,
            model_id=route.model_id,
            messages=messages,
            max_tokens=route.max_tokens,
        )

        if response:
            logger.info(f"[Router] ✓ Success: {route.name}")
            return response, route.name

        logger.warning(f"[Router] ✗ Failed: {route.name}")

    logger.error(f"[Router] ALL {len(routes)} routes failed!")
    return "", "none"