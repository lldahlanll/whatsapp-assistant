# app/ai/__init__.py
from app.ai.circuit_breaker import CircuitBreaker
from app.ai.client import multi_client
from app.ai.models import (
    MODELS,
    TIER_CONFIGS,
    ModelRoute,
    ModelTier,
    TierConfig,
    get_fallback_routes,
)
from app.ai.providers import ProviderType
from app.ai.router import classify_message, route_and_generate

# Backward compatibility
openrouter_client = multi_client

__all__ = [
    "multi_client",
    "openrouter_client",  # alias backward-compat
    "CircuitBreaker",
    "MODELS",
    "TIER_CONFIGS",
    "ModelTier",
    "ModelRoute",
    "TierConfig",
    "ProviderType",
    "get_fallback_routes",
    "classify_message",
    "route_and_generate",
]