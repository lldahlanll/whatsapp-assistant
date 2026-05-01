# app/ai/models.py
"""
Model routing — multi-provider, free-tier only.

Perubahan v1.1:
- TIER_3: Reorder routes — Groq & Gemini Flash naik priority,
  Gemini Pro turun (quota 25 req/hari sangat terbatas)
- Nemotron tetap ada sebagai fallback terakhir
"""
from dataclasses import dataclass, field
from enum import Enum

from app.ai.providers import ProviderType


class ModelTier(Enum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


@dataclass(frozen=True)
class ModelRoute:
    name: str
    provider_type: ProviderType
    endpoint_name: str
    model_id: str
    max_tokens: int


@dataclass(frozen=True)
class TierConfig:
    tier: ModelTier
    description: str
    routes: list[ModelRoute] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# TIER 1: Pesan pendek/casual (latency priority)
# ──────────────────────────────────────────────────────────────
TIER_1_ROUTES = [
    ModelRoute(
        name="Groq Llama 3.1 8B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="llama-3.1-8b-instant",
        max_tokens=1024,
    ),
    ModelRoute(
        name="Groq Llama 4 Scout 17B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=1024,
    ),
    ModelRoute(
        name="Gemini 2.5 Flash-Lite (acc1)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc1",
        model_id="gemini-2.5-flash-lite",
        max_tokens=1024,
    ),
    ModelRoute(
        name="Gemini 2.5 Flash-Lite (acc2)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc2",
        model_id="gemini-2.5-flash-lite",
        max_tokens=1024,
    ),
    ModelRoute(
        name="OpenRouter Gemma 4 26B (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="google/gemma-4-26b-a4b-it:free",
        max_tokens=1024,
    ),
]


# ──────────────────────────────────────────────────────────────
# TIER 2: Reasoning medium (balance quality & speed)
# ──────────────────────────────────────────────────────────────
TIER_2_ROUTES = [
    ModelRoute(
        name="Gemini 2.5 Flash (acc1)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc1",
        model_id="gemini-2.5-flash",
        max_tokens=2048,
    ),
    ModelRoute(
        name="Gemini 2.5 Flash (acc2)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc2",
        model_id="gemini-2.5-flash",
        max_tokens=2048,
    ),
    ModelRoute(
        name="Groq Llama 3.3 70B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="llama-3.3-70b-versatile",
        max_tokens=2048,
    ),
    ModelRoute(
        name="Groq Qwen3 32B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="qwen/qwen3-32b",
        max_tokens=2048,
    ),
    ModelRoute(
        name="Groq GPT-OSS 120B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="openai/gpt-oss-120b",
        max_tokens=2048,
    ),
    ModelRoute(
        name="OpenRouter MiniMax M2.5 (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="minimax/minimax-m2.5:free",
        max_tokens=2048,
    ),
    ModelRoute(
        name="OpenRouter MiniMax M2.5 (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="minimax/minimax-m2.5:free",
        max_tokens=2048,
    ),
    ModelRoute(
        name="OpenRouter Gemma 4 26B (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="google/gemma-4-26b-a4b-it:free",
        max_tokens=2048,
    ),
    ModelRoute(
        name="OpenRouter GPT-OSS 120B (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="openai/gpt-oss-120b:free",
        max_tokens=2048,
    ),
]


# ──────────────────────────────────────────────────────────────
# TIER 3: Tugas kompleks/teknikal (quality priority)
#
# ⚠️  REORDER v1.1:
#   Groq 70B/Qwen3 naik ke PRIMARY — cepat & reliable
#   Gemini Flash naik ke secondary — quota lebih longgar dari Pro
#   Gemini Pro turun ke LAST RESORT — quota hanya 25 req/hari!
#   Nemotron tetap sebagai deep fallback
# ──────────────────────────────────────────────────────────────
TIER_3_ROUTES = [
    # ── PRIMARY: Groq — paling cepat, quota generous ──────────
    ModelRoute(
        name="Groq Qwen3 32B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="qwen/qwen3-32b",
        max_tokens=4096,
    ),
    ModelRoute(
        name="Groq GPT-OSS 120B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="openai/gpt-oss-120b",
        max_tokens=4096,
    ),
    ModelRoute(
        name="Groq Llama 3.3 70B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="llama-3.3-70b-versatile",
        max_tokens=4096,
    ),

    # ── SECONDARY: Gemini Flash — quota lebih longgar dari Pro ─
    ModelRoute(
        name="Gemini 2.5 Flash (acc1)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc1",
        model_id="gemini-2.5-flash",
        max_tokens=4096,
    ),
    ModelRoute(
        name="Gemini 2.5 Flash (acc2)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc2",
        model_id="gemini-2.5-flash",
        max_tokens=4096,
    ),

    # ── TERTIARY: OpenRouter Qwen3 Coder — bagus untuk coding ─
    ModelRoute(
        name="OpenRouter Qwen3 Coder (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="qwen/qwen3-coder:free",
        max_tokens=4096,
    ),
    ModelRoute(
        name="OpenRouter Qwen3 Coder (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="qwen/qwen3-coder:free",
        max_tokens=4096,
    ),

    # ── FALLBACK: OpenRouter GPT-OSS ──────────────────────────
    ModelRoute(
        name="OpenRouter GPT-OSS 120B (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="openai/gpt-oss-120b:free",
        max_tokens=4096,
    ),
    ModelRoute(
        name="OpenRouter GPT-OSS 120B (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="openai/gpt-oss-120b:free",
        max_tokens=4096,
    ),

    # ── DEEP FALLBACK: Nemotron — lambat tapi powerful ────────
    ModelRoute(
        name="OpenRouter Nemotron 120B (acc1)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc1",
        model_id="nvidia/nemotron-3-super-120b-a12b:free",
        max_tokens=4096,
    ),
    ModelRoute(
        name="OpenRouter Nemotron 120B (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="nvidia/nemotron-3-super-120b-a12b:free",
        max_tokens=4096,
    ),

    # ── LAST RESORT: Gemini Pro — hemat untuk yang benar penting
    # Quota: 25 req/hari per akun — gunakan hanya kalau semua di atas gagal
    ModelRoute(
        name="Gemini 2.5 Pro (acc1)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc1",
        model_id="gemini-2.5-pro",
        max_tokens=4096,
    ),
    ModelRoute(
        name="Gemini 2.5 Pro (acc2)",
        provider_type=ProviderType.GEMINI,
        endpoint_name="gemini-acc2",
        model_id="gemini-2.5-pro",
        max_tokens=4096,
    ),
]


TIER_CONFIGS: dict[ModelTier, TierConfig] = {
    ModelTier.TIER_1: TierConfig(
        tier=ModelTier.TIER_1,
        description="Pesan pendek/casual",
        routes=TIER_1_ROUTES,
    ),
    ModelTier.TIER_2: TierConfig(
        tier=ModelTier.TIER_2,
        description="Reasoning medium",
        routes=TIER_2_ROUTES,
    ),
    ModelTier.TIER_3: TierConfig(
        tier=ModelTier.TIER_3,
        description="Tugas kompleks/teknikal",
        routes=TIER_3_ROUTES,
    ),
}


def get_fallback_routes(start_tier: ModelTier) -> list[ModelRoute]:
    """Graceful degradation: T3 → T2 → T1."""
    descending = [ModelTier.TIER_3, ModelTier.TIER_2, ModelTier.TIER_1]
    start_idx = descending.index(start_tier)
    routes: list[ModelRoute] = []
    for tier in descending[start_idx:]:
        routes.extend(TIER_CONFIGS[tier].routes)
    return routes


# Backward compatibility
MODELS: dict[ModelTier, ModelRoute] = {
    tier: cfg.routes[0]
    for tier, cfg in TIER_CONFIGS.items()
}


# ──────────────────────────────────────────────────────────────
# 🛡️ FREE-TIER SAFETY ASSERTION
# ──────────────────────────────────────────────────────────────

FREE_TIER_WHITELIST: dict[ProviderType, set[str]] = {
    ProviderType.GROQ: {
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
    },
    ProviderType.GEMINI: {
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemma-3-27b-it",
        "gemma-3-12b-it",
    },
    ProviderType.OPENROUTER: set(),  # Validated by ":free" suffix
}


def assert_free_tier_only() -> None:
    """Sanity check: pastikan semua routes pakai model gratis."""
    violations: list[str] = []

    for tier_cfg in TIER_CONFIGS.values():
        for route in tier_cfg.routes:
            provider = route.provider_type
            model_id = route.model_id

            if provider == ProviderType.OPENROUTER:
                if not model_id.endswith(":free"):
                    violations.append(
                        f"OpenRouter '{route.name}' → {model_id} "
                        f"(missing ':free' suffix)"
                    )
                continue

            whitelist = FREE_TIER_WHITELIST.get(provider, set())
            if model_id not in whitelist:
                violations.append(
                    f"{provider.value} '{route.name}' → {model_id} "
                    f"(tidak ada di FREE_TIER_WHITELIST)"
                )

    if violations:
        msg = (
            "\n⚠️  FREE-TIER SAFETY CHECK FAILED ⚠️\n"
            + "\n".join(f"  ❌ {v}" for v in violations)
        )
        raise AssertionError(msg)