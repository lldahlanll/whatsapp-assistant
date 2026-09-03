"""Unit tests for AIService orchestrator, circuit breaker, and provider fallback."""

import asyncio

import pytest

from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    AllProvidersExhaustedError,
    ILLMProvider,
    ProviderError,
    ProviderMessage,
    RateLimitError,
)
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy


class MockProvider(ILLMProvider):
    def __init__(self, name: str, behavior: str = "success") -> None:
        self._name = name
        self._behavior = behavior
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, messages: list[ProviderMessage], api_key: str, model: str) -> AIResponse:
        self.call_count += 1
        if self._behavior == "429":
            raise RateLimitError("Rate limit exceeded", retry_after=0.04)
        if self._behavior == "500":
            raise ProviderError("Server error 500")
        return AIResponse(
            text=f"Reply from {self._name}",
            provider_used=self._name,
            key_index_used=0,
            token_usage={"total_tokens": 50},
            latency_ms=10.0,
        )


@pytest.mark.asyncio
async def test_ai_service_primary_provider_success():
    p1 = MockProvider("gemini", "success")
    p2 = MockProvider("groq", "success")

    providers = {
        "gemini": (p1, KeyPool(["gkey1"])),
        "groq": (p2, KeyPool(["gkey2"])),
    }
    strategy = FixedPriorityStrategy(["gemini", "groq"])
    service = AIService(providers, strategy)

    res = await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi")])
    assert res.provider_used == "gemini"
    assert res.text == "Reply from gemini"
    assert p1.call_count == 1
    assert p2.call_count == 0


@pytest.mark.asyncio
async def test_ai_service_fallback_on_rate_limit():
    p1 = MockProvider("gemini", "429")
    p2 = MockProvider("groq", "success")

    providers = {
        "gemini": (p1, KeyPool(["gkey1"], default_cooldown_seconds=0.1)),
        "groq": (p2, KeyPool(["gkey2"])),
    }
    strategy = FixedPriorityStrategy(["gemini", "groq"])
    service = AIService(providers, strategy)

    res = await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi")])
    assert res.provider_used == "groq"
    assert res.text == "Reply from groq"
    assert p1.call_count == 1
    assert p2.call_count == 1


@pytest.mark.asyncio
async def test_ai_service_circuit_breaker_skips_cooling_provider():
    p1 = MockProvider("gemini", "429")
    p2 = MockProvider("groq", "success")

    providers = {
        "gemini": (p1, KeyPool(["gkey1"], default_cooldown_seconds=10.0)),
        "groq": (p2, KeyPool(["gkey2"])),
    }
    strategy = FixedPriorityStrategy(["gemini", "groq"])
    service = AIService(providers, strategy)

    # First call triggers 429 on gemini and trips circuit breaker
    res1 = await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi")])
    assert res1.provider_used == "groq"
    assert p1.call_count == 1

    # Second call should skip gemini directly without calling generate()
    res2 = await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi again")])
    assert res2.provider_used == "groq"
    assert p1.call_count == 1  # count did not increase!


@pytest.mark.asyncio
async def test_ai_service_circuit_breaker_recovery():
    """C10 recovery test: provider circuit breaker recovers after cooldown window."""
    p1 = MockProvider("gemini", "429")
    p2 = MockProvider("groq", "success")

    # Short cooldown 0.05s
    providers = {
        "gemini": (p1, KeyPool(["gkey1"], default_cooldown_seconds=0.05)),
        "groq": (p2, KeyPool(["gkey2"])),
    }
    strategy = FixedPriorityStrategy(["gemini", "groq"])
    service = AIService(providers, strategy)

    # First call trips gemini 429
    await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi")])
    assert p1.call_count == 1

    # Wait for cooldown to expire
    await asyncio.sleep(0.08)

    # Change gemini behavior to success
    p1._behavior = "success"

    # Next call should try gemini again!
    res = await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi after recovery")])
    assert res.provider_used == "gemini"
    assert p1.call_count == 2


@pytest.mark.asyncio
async def test_ai_service_all_exhausted_raises_error():
    p1 = MockProvider("gemini", "429")
    p2 = MockProvider("groq", "429")

    providers = {
        "gemini": (p1, KeyPool(["gkey1"], default_cooldown_seconds=10.0)),
        "groq": (p2, KeyPool(["gkey2"], default_cooldown_seconds=10.0)),
    }
    strategy = FixedPriorityStrategy(["gemini", "groq"])
    service = AIService(providers, strategy)

    with pytest.raises(AllProvidersExhaustedError):
        await service.generate_reply("chat1", [ProviderMessage(role="user", content="hi")])
