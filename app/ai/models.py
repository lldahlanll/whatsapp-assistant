# app/ai/models.py
"""
Model routing — multi-provider, free-tier only.
Updated dengan 5 OpenRouter models tambahan.
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
    # PRIMARY: Groq Llama 3.1 8B — paling cepat
    ModelRoute(
        name="Groq Llama 3.1 8B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="llama-3.1-8b-instant",
        max_tokens=1024,
    ),
    # FALLBACK: Groq Llama 4 Scout 17B MoE
    ModelRoute(
        name="Groq Llama 4 Scout 17B",
        provider_type=ProviderType.GROQ,
        endpoint_name="groq-main",
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=1024,
    ),
    # FALLBACK: Gemini Flash-Lite ×2
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
    # LAST RESORT: OpenRouter Gemma 4 (kecil & cepat)
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
    # PRIMARY: Gemini 2.5 Flash ×2
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
    # FALLBACK: Groq models (cepat & strong)
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
    # OpenRouter: MiniMax M2.5 (versatile, modern)
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
    # OpenRouter: Gemma 4 sebagai extra fallback
    ModelRoute(
        name="OpenRouter Gemma 4 26B (acc2)",
        provider_type=ProviderType.OPENROUTER,
        endpoint_name="openrouter-acc2",
        model_id="google/gemma-4-26b-a4b-it:free",
        max_tokens=2048,
    ),
    # LAST RESORT: GPT-OSS via OpenRouter
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
# ──────────────────────────────────────────────────────────────
TIER_3_ROUTES = [
    # PRIMARY: Gemini 2.5 Pro ×2 — best reasoning
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
    # PRIMARY: Qwen3 Coder via OpenRouter — specialized untuk coding
    # Bot Anda fokus productivity → query coding sering masuk
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
    # FALLBACK: Nemotron 120B — flagship NVIDIA
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
    # FALLBACK: Groq models (faster fallback)
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
    # LAST RESORT: GPT-OSS via OpenRouter
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
    # OpenRouter: validated by ":free" suffix check
    ProviderType.OPENROUTER: set(),
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
                        f"(missing ':free' suffix, akan dikenai biaya!)"
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
            "Routes berikut TIDAK terverifikasi sebagai free tier:\n"
            + "\n".join(f"  ❌ {v}" for v in violations)
            + "\n\nPilihan:\n"
            "  1. Ganti model ke yang ada di whitelist\n"
            "  2. Tambahkan model ke FREE_TIER_WHITELIST kalau yakin gratis\n"
            "  3. Untuk OpenRouter, pastikan model_id berakhiran ':free'\n"
        )
        raise AssertionError(msg)