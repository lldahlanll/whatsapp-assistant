import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from loguru import logger


class ProviderType(Enum):
    GROQ = "groq"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


@dataclass(frozen=True)
class ProviderEndpoint:
    """Konfigurasi satu API key/endpoint."""
    provider_type: ProviderType
    name: str  # untuk logging: "groq-main", "gemini-acc1", dll
    api_key: str
    base_url: str
    extra_headers: dict[str, str] = None


class BaseProvider(ABC):
    """Interface yang harus diimplement setiap provider."""

    def __init__(self, endpoint: ProviderEndpoint):
        self.endpoint = endpoint
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
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]:
        """Auth headers spesifik tiap provider."""
        ...

    @abstractmethod
    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        """Return response text atau None kalau gagal."""
        ...


# ── Groq Provider ─────────────────────────────────────────────

class GroqProvider(BaseProvider):
    """OpenAI-compatible. Endpoint: https://api.groq.com/openai/v1"""

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
            return _parse_openai_compatible(r, self.endpoint.name, model_id)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"[{self.endpoint.name}] Network error: {e}")
            return None


# ── Gemini Provider ───────────────────────────────────────────

class GeminiProvider(BaseProvider):
    """Google Gemini native API (bukan OpenAI-compatible)."""

    def _auth_headers(self) -> dict[str, str]:
        # Gemini pakai key di query param, tapi kita simpan di header juga untuk konsistensi
        return {}

    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
    ) -> Optional[str]:
        try:
            client = await self._get_client()

            # Convert OpenAI format → Gemini format
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
        """OpenAI format → Gemini format."""
        system_instruction = ""
        gemini_contents = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                # Gemini pakai systemInstruction terpisah
                system_instruction = content
            elif role == "assistant":
                gemini_contents.append({
                    "role": "model",
                    "parts": [{"text": content}],
                })
            else:  # user
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })
        return gemini_contents, system_instruction


# ── OpenRouter Provider ───────────────────────────────────────

class OpenRouterProvider(BaseProvider):
    """OpenAI-compatible aggregator."""

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
    """Parse response untuk OpenAI-compatible APIs (Groq, OpenRouter)."""
    if response.status_code != 200:
        # Log dengan detail tambahan untuk 429 upstream
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

def create_provider(endpoint: ProviderEndpoint) -> BaseProvider:
    mapping = {
        ProviderType.GROQ: GroqProvider,
        ProviderType.GEMINI: GeminiProvider,
        ProviderType.OPENROUTER: OpenRouterProvider,
    }
    return mapping[endpoint.provider_type](endpoint)