from typing import Optional

from loguru import logger

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.providers import (
    BaseProvider,
    ProviderEndpoint,
    ProviderType,
    create_provider,
)
from app.config import settings


class MultiProviderClient:
    """
    Pool dari semua provider endpoints yang dikonfigurasi.

    Auto-skip endpoint yang:
    - API key-nya tidak diset
    - Lagi di-trip oleh circuit breaker
    """

    def __init__(self) -> None:
        self.providers: dict[str, BaseProvider] = {}
        self.breaker = CircuitBreaker(
            disable_duration=settings.circuit_breaker_disable_duration
        )
        self._register_endpoints()

    def _register_endpoints(self) -> None:
        """Register semua endpoint yang punya API key valid."""
        endpoints = self._build_endpoints()

        for ep in endpoints:
            if not ep.api_key:
                logger.debug(f"[Client] Skip {ep.name}: no API key")
                continue
            self.providers[ep.name] = create_provider(ep)
            logger.info(f"[Client] ✓ Registered: {ep.name} ({ep.provider_type.value})")

        if not self.providers:
            logger.error("[Client] ⚠️ No providers registered! Check your .env")

    @staticmethod
    def _build_endpoints() -> list[ProviderEndpoint]:
        return [
            ProviderEndpoint(
                provider_type=ProviderType.GROQ,
                name="groq-main",
                api_key=settings.groq_api_key or "",
                base_url=settings.groq_base_url,
            ),
            ProviderEndpoint(
                provider_type=ProviderType.GEMINI,
                name="gemini-acc1",
                api_key=settings.gemini_api_key_1 or "",
                base_url=settings.gemini_base_url,
            ),
            ProviderEndpoint(
                provider_type=ProviderType.GEMINI,
                name="gemini-acc2",
                api_key=settings.gemini_api_key_2 or "",
                base_url=settings.gemini_base_url,
            ),
            ProviderEndpoint(
                provider_type=ProviderType.OPENROUTER,
                name="openrouter-acc1",
                api_key=settings.openrouter_api_key_1 or "",
                base_url=settings.openrouter_base_url,
            ),
            ProviderEndpoint(
                provider_type=ProviderType.OPENROUTER,
                name="openrouter-acc2",
                api_key=settings.openrouter_api_key_2 or "",
                base_url=settings.openrouter_base_url,
            ),
        ]

    async def call(
        self,
        endpoint_name: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        """
        Panggil model di endpoint tertentu.
        Return None kalau endpoint tidak terdaftar, breaker tripped, atau call gagal.
        """
        provider = self.providers.get(endpoint_name)
        if not provider:
            logger.debug(f"[Client] Skip {endpoint_name}: not registered")
            return None

        # Circuit breaker key = endpoint:model untuk granularity
        breaker_key = f"{endpoint_name}:{model_id}"
        if await self.breaker.is_open(breaker_key):
            return None

        response = await provider.generate(model_id, messages, max_tokens)

        # Trip breaker kalau gagal — tapi hanya untuk error berat
        # (network errors are transient, jangan trip)
        # Logic trip ada di provider.generate() melalui logging level

        return response

    async def trip(self, endpoint_name: str, model_id: str, reason: str) -> None:
        """Manual trip breaker untuk endpoint:model."""
        await self.breaker.trip(f"{endpoint_name}:{model_id}", reason)

    async def close(self) -> None:
        """Tutup semua HTTP clients."""
        for name, provider in self.providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"[Client] Error closing {name}: {e}")
        logger.info("[Client] All providers closed")

    def status(self) -> dict:
        """Untuk health endpoint."""
        return {
            "registered_endpoints": list(self.providers.keys()),
            "total": len(self.providers),
        }


# Singleton
multi_client = MultiProviderClient()