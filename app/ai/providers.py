# app/ai/providers.py
"""
Provider implementations dengan smart error classification.

Error classification:
- 401/403     → PERMANENT failure  → trip circuit breaker (disable 1 jam)
- 429 quota   → DAILY limit        → trip circuit breaker (disable sampai besok)
- 429 rate    → TRANSIENT          → skip (jangan trip, coba lagi nanti)
- 404         → MODEL not found    → trip circuit breaker (disable 1 jam)
- 5xx         → TRANSIENT server   → skip (retry fallback)
- network err → TRANSIENT          → skip
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from app.ai.circuit_breaker import CircuitBreaker


class ProviderType(Enum):
    GROQ = "groq"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


@dataclass(frozen=True)
class ProviderEndpoint:
    """Konfigurasi satu API key/endpoint."""
    provider_type: ProviderType
    name: str
    api_key: str
    base_url: str
    extra_headers: dict[str, str] = None


# ── Error Classification ──────────────────────────────────────

class FailureType(Enum):
    TRANSIENT   = "transient"    # Retry nanti — jangan trip breaker
    QUOTA       = "quota"        # Daily limit habis — trip sampai besok
    AUTH        = "auth"         # Key invalid/expired — trip 1 jam
    MODEL       = "model"        # Model tidak ada — trip 1 jam
    UPSTREAM    = "upstream"     # Provider upstream down — skip sementara


def _seconds_until_midnight() -> int:
    """Hitung detik sampai tengah malam UTC (quota reset Gemini)."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(int((midnight - now).total_seconds()), 3600)


def classify_http_error(
    status_code: int,
    body: str,
    provider_type: ProviderType,
) -> FailureType:
    """
    Klasifikasi error HTTP ke FailureType.

    Important nuance untuk 429:
    - Groq      : 429 = TPM (Tokens Per Minute) limit, reset per menit
                  → FailureType.UPSTREAM (short trip 60s)
    - Gemini    : 429 = Daily quota exhausted, reset midnight UTC
                  → FailureType.QUOTA (long trip until midnight)
    - OpenRouter: 429 bisa "upstream rate-limited" (transient) atau quota
                  → Cek body content untuk klasifikasi
    """
    body_lower = body.lower()

    if status_code in (401, 403):
        return FailureType.AUTH

    if status_code == 404:
        return FailureType.MODEL

    if status_code == 429:
        # ── Groq: 429 selalu TPM-based, BUKAN daily quota ────
        # Signal: "tokens per minute", "TPM", "service tier"
        if provider_type == ProviderType.GROQ:
            tpm_signals = [
                "tokens per minute",
                "tpm",
                "service tier",
                "rate limit reached",
            ]
            if any(s in body_lower for s in tpm_signals):
                return FailureType.UPSTREAM  # Short trip
            return FailureType.TRANSIENT

        # ── Gemini & OpenRouter: bedakan quota vs rate ───────
        quota_signals = [
            "exceeded your current quota",
            "billing",
            "daily limit",
            "resource_exhausted",
            "quota exceeded",
        ]
        rate_signals = [
            "rate limit",
            "rate-limit",
            "too many requests",
            "retry shortly",
            "temporarily rate-limited",
            "upstream",
        ]

        if any(s in body_lower for s in quota_signals):
            return FailureType.QUOTA

        if any(s in body_lower for s in rate_signals):
            return FailureType.UPSTREAM

        return FailureType.TRANSIENT

    if status_code >= 500:
        return FailureType.TRANSIENT

    return FailureType.TRANSIENT


def get_trip_duration(failure_type: FailureType, provider_type: ProviderType) -> Optional[int]:
    """
    Return durasi trip dalam detik, atau None kalau tidak perlu trip.

    Logika:
    - AUTH    → 3600s (1 jam) — beri waktu user fix key
    - MODEL   → 3600s (1 jam)
    - QUOTA   → sampai tengah malam UTC (Gemini reset harian)
    - UPSTREAM:
        * Groq      → 70s (TPM reset per menit, kasih buffer)
        * OpenRouter → 300s (5 menit untuk upstream issue)
        * Lainnya   → None (jangan trip)
    - TRANSIENT → None (jangan trip)
    """
    if failure_type == FailureType.AUTH:
        return 3600

    if failure_type == FailureType.MODEL:
        return 3600

    if failure_type == FailureType.QUOTA:
        # Gemini quota reset tengah malam UTC
        if provider_type == ProviderType.GEMINI:
            secs = _seconds_until_midnight()
            logger.info(
                f"[Provider] Gemini quota exceeded → "
                f"trip {secs}s ({secs/3600:.1f}h until midnight UTC)"
            )
            return secs
        # Provider lain: 1 jam default untuk quota
        return 3600

    if failure_type == FailureType.UPSTREAM:
        # Groq TPM: reset per menit. Trip 70s (60s + buffer 10s)
        if provider_type == ProviderType.GROQ:
            return 70
        # OpenRouter upstream issues: cooldown 5 menit
        if provider_type == ProviderType.OPENROUTER:
            return 300
        return None  # Provider lain: jangan trip

    return None  # TRANSIENT → jangan trip


# ─────────────────────────────────────────────────────────────
# Base Provider
# ─────────────────────────────────────────────────────────────

class BaseProvider(ABC):
    def __init__(
        self,
        endpoint: ProviderEndpoint,
        breaker: Optional["CircuitBreaker"] = None,
    ):
        self.endpoint = endpoint
        self._breaker = breaker
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                **self._auth_headers(),
                **(self.endpoint.extra_headers or {}),
            }
            self._client = httpx.AsyncClient(
                base_url=self.endpoint.base_url,
                headers=headers,
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]: ...

    @abstractmethod
    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]: ...

    async def _maybe_trip_breaker(
        self,
        model_id: str,
        status_code: int,
        body: str,
    ) -> None:
        """
        Evaluasi apakah circuit breaker perlu di-trip berdasarkan error.
        Dipanggil setelah setiap response non-200.
        """
        if self._breaker is None:
            return

        failure_type = classify_http_error(
            status_code, body, self.endpoint.provider_type
        )
        duration = get_trip_duration(failure_type, self.endpoint.provider_type)

        if duration is not None:
            breaker_key = f"{self.endpoint.name}:{model_id}"
            reason = f"HTTP {status_code} ({failure_type.value})"
            await self._breaker.trip_with_duration(breaker_key, reason, duration)
            logger.warning(
                f"[Provider] 🔴 Circuit tripped: {breaker_key} "
                f"| {failure_type.value} | {duration}s"
            )


# ── Groq Provider ─────────────────────────────────────────────

class GroqProvider(BaseProvider):

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.endpoint.api_key}"}

    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        try:
            client = await self._get_client()
            r = await client.post(
                "/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
            if r.status_code != 200:
                await self._maybe_trip_breaker(model_id, r.status_code, r.text)
            return _parse_openai_compatible(r, self.endpoint.name, model_id)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"[{self.endpoint.name}] Network error: {e}")
            return None


# ── Gemini Provider ───────────────────────────────────────────

class GeminiProvider(BaseProvider):

    def _auth_headers(self) -> dict[str, str]:
        return {}

    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        try:
            client = await self._get_client()
            gemini_contents, system_instruction = self._convert_messages(messages)

            payload = {
                "contents": gemini_contents,
                "generationConfig": {"maxOutputTokens": max_tokens},
            }
            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            r = await client.post(
                f"/models/{model_id}:generateContent",
                params={"key": self.endpoint.api_key},
                json=payload,
            )

            if r.status_code != 200:
                await self._maybe_trip_breaker(model_id, r.status_code, r.text)
                logger.warning(
                    f"[{self.endpoint.name}] HTTP {r.status_code} | "
                    f"{model_id} | {r.text[:200]}"
                )
                return None

            data = r.json()
            candidates = data.get("candidates", [])
            if not candidates:
                logger.warning(f"[{self.endpoint.name}] No candidates in response")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()

            if not text:
                logger.warning(f"[{self.endpoint.name}] Empty response")
                return None

            tokens = data.get("usageMetadata", {}).get("totalTokenCount", "?")
            logger.debug(f"[{self.endpoint.name}] ✓ {model_id} | tokens: {tokens}")
            return text

        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"[{self.endpoint.name}] Network error: {e}")
            return None

    @staticmethod
    def _convert_messages(messages: list[dict]) -> tuple[list[dict], str]:
        system_instruction = ""
        gemini_contents = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            elif role == "assistant":
                gemini_contents.append({
                    "role": "model",
                    "parts": [{"text": content}],
                })
            else:
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })
        return gemini_contents, system_instruction


# ── OpenRouter Provider ───────────────────────────────────────

class OpenRouterProvider(BaseProvider):

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.endpoint.api_key}",
            "HTTP-Referer": "https://github.com/whatsapp-ai-bot",
            "X-Title": "WhatsApp AI Bot",
        }

    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        try:
            client = await self._get_client()
            r = await client.post(
                "/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
            if r.status_code != 200:
                await self._maybe_trip_breaker(model_id, r.status_code, r.text)
            return _parse_openai_compatible(r, self.endpoint.name, model_id)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"[{self.endpoint.name}] Network error: {e}")
            return None


# ── Helper ────────────────────────────────────────────────────

def _parse_openai_compatible(
    response: httpx.Response,
    endpoint_name: str,
    model_id: str,
) -> Optional[str]:
    if response.status_code != 200:
        body_preview = response.text[:200]
        is_upstream_429 = (
            response.status_code == 429
            and "upstream" in response.text.lower()
        )
        marker = "UPSTREAM" if is_upstream_429 else "DIRECT"
        logger.warning(
            f"[{endpoint_name}] HTTP {response.status_code} {marker} | "
            f"{model_id} | {body_preview}"
        )
        return None

    try:
        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            logger.warning(f"[{endpoint_name}] Empty response from {model_id}")
            return None

        tokens = data.get("usage", {}).get("total_tokens", "?")
        logger.debug(f"[{endpoint_name}] ✓ {model_id} | tokens: {tokens}")
        return content
    except (ValueError, KeyError, IndexError) as e:
        logger.error(f"[{endpoint_name}] Parse error: {e}")
        return None


# ── Factory ───────────────────────────────────────────────────

def create_provider(
    endpoint: ProviderEndpoint,
    breaker: Optional["CircuitBreaker"] = None,
) -> BaseProvider:
    mapping = {
        ProviderType.GROQ:       GroqProvider,
        ProviderType.GEMINI:     GeminiProvider,
        ProviderType.OPENROUTER: OpenRouterProvider,
    }
    return mapping[endpoint.provider_type](endpoint, breaker)