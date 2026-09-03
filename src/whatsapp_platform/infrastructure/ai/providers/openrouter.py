"""OpenRouter LLM provider adapter.

Rate-limit signal (C3 — researched from OpenRouter API docs):
- HTTP 429 status code
- Optional Retry-After HTTP header (integer seconds) — may be absent
- JSON body: { "error": { "code": 429, "message": "...", "metadata": { ... } } }
  The metadata may include provider_code for upstream provider errors.

Fallback: if Retry-After header is absent or unparseable → cooldown_default.

Shared httpx.AsyncClient injected via constructor (C4).
"""

from __future__ import annotations

import time

import httpx
import structlog

from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    ILLMProvider,
    ProviderError,
    ProviderMessage,
    RateLimitError,
)

logger = structlog.get_logger()

_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"


def _parse_openrouter_retry_after(response: httpx.Response, default: float) -> float:
    """Parse optional Retry-After header from OpenRouter 429 response.

    OpenRouter may include a Retry-After header (integer seconds) but it's not
    guaranteed — falls back to default when absent or unparseable (C3).
    """
    header = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except (ValueError, TypeError):
            pass
    return default


class OpenRouterProvider(ILLMProvider):
    """Adapter for OpenRouter OpenAI-compatible chat completions API."""

    def __init__(self, client: httpx.AsyncClient, cooldown_default: float = 60.0) -> None:
        self._client = client
        self._cooldown_default = cooldown_default

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def generate(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Call OpenRouter chat completions endpoint (OpenAI-compatible)."""
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter requires HTTP-Referer for identification
            "HTTP-Referer": "https://github.com/whatsapp-platform",
            "X-Title": "WhatsApp Platform AI",
        }

        start = time.monotonic()
        try:
            response = await self._client.post(
                _OPENROUTER_API_BASE, json=payload, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenRouter network error: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code == 429:
            retry_after = _parse_openrouter_retry_after(response, self._cooldown_default)
            raise RateLimitError(
                f"OpenRouter rate limit (retry in {retry_after:.1f}s)", retry_after=retry_after
            )

        if not response.is_success:
            body = _safe_json(response)
            error_obj = body.get("error", {})
            error_msg = (
                error_obj.get("message", response.text[:200])
                if isinstance(error_obj, dict)
                else response.text[:200]
            )
            raise ProviderError(f"OpenRouter error {response.status_code}: {error_msg}")

        data = _safe_json(response)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"OpenRouter unexpected response shape: {exc}") from exc

        # Extract token usage if provided
        token_usage: dict[str, int] | None = None
        usage = data.get("usage")
        if usage:
            token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return AIResponse(
            text=text,
            provider_used=self.provider_name,
            key_index_used=-1,  # filled in by AIService
            token_usage=token_usage,
            latency_ms=latency_ms,
        )


def _safe_json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {}
