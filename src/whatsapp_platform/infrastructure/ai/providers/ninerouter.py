"""9router LLM provider adapter.

9router adalah self-hosted OpenAI-compatible LLM router.
Endpoint: POST {base_url}/chat/completions

Rate-limit signal:
- HTTP 429 status code
- Optional Retry-After HTTP header (integer seconds)
- Fallback ke cooldown_default jika header tidak ada

Tool calling menggunakan format OpenAI standard.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    ILLMProvider,
    ProviderError,
    ProviderMessage,
    RateLimitError,
    ToolCall,
)
from whatsapp_platform.infrastructure.ai.providers.openai_format import build_openai_content

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition

logger = structlog.get_logger()


def _parse_retry_after(response: httpx.Response, default: float) -> float:
    """Parse Retry-After header, fallback ke default."""
    header = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except (ValueError, TypeError):
            pass
    return default


def _build_openai_messages(messages: list[ProviderMessage]) -> list[dict[str, Any]]:
    """Format ProviderMessage list ke OpenAI-compatible messages format."""
    result: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "name": m.name or "",
                "content": m.content,
            })
        elif m.role == "assistant" and m.tool_calls:
            tcs: list[dict[str, Any]] = []
            for tc in m.tool_calls:
                args_str = (
                    json.dumps(tc.arguments, ensure_ascii=False)
                    if isinstance(tc.arguments, dict)
                    else str(tc.arguments)
                )
                tcs.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": args_str,
                    },
                })
            entry: dict[str, Any] = {"role": "assistant", "tool_calls": tcs}
            if m.content:
                entry["content"] = m.content
            result.append(entry)
        else:
            result.append({"role": m.role, "content": build_openai_content(m)})
    return result


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class NineRouterProvider(ILLMProvider):
    """Adapter untuk 9router self-hosted OpenAI-compatible LLM router."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        cooldown_default: float = 60.0,
    ) -> None:
        self._client = client
        cleaned = base_url.rstrip("/")
        if not cleaned.endswith("/chat/completions"):
            self._endpoint = f"{cleaned}/chat/completions"
        else:
            self._endpoint = cleaned
        self._cooldown_default = cooldown_default

    @property
    def provider_name(self) -> str:
        return "ninerouter"

    @property
    def supports_tool_calling(self) -> bool:
        return True

    async def generate(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
    ) -> AIResponse:
        return await self._generate_internal(messages, api_key, model, tools=None)

    async def generate_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: list[ToolDefinition],
        api_key: str,
        model: str,
    ) -> AIResponse:
        return await self._generate_internal(messages, api_key, model, tools=tools)

    async def _generate_internal(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> AIResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": _build_openai_messages(messages),
        }
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]
            payload["tool_choice"] = "auto"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Title": "WhatsApp Platform AI",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        start = time.monotonic()
        try:
            response = await self._client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"9router request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"9router network error: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code == 429:
            retry_after = _parse_retry_after(response, self._cooldown_default)
            raise RateLimitError(
                f"9router rate limit (retry in {retry_after:.1f}s)",
                retry_after=retry_after,
            )

        if not response.is_success:
            body = _safe_json(response)
            error_msg = (
                body.get("error", {}).get("message", response.text[:200])
                if isinstance(body.get("error"), dict)
                else response.text[:200]
            )
            raise ProviderError(f"9router error {response.status_code}: {error_msg}")

        data = _safe_json(response)
        try:
            choice = data["choices"][0]["message"]
            text = choice.get("content") or ""
            raw_tool_calls = choice.get("tool_calls")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"9router unexpected response shape: {exc}") from exc

        tool_calls: list[ToolCall] = []
        if raw_tool_calls and isinstance(raw_tool_calls, list):
            for rtc in raw_tool_calls:
                fn = rtc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args_raw = fn.get("arguments", "{}")
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except Exception:
                    fn_args = {}
                tool_calls.append(
                    ToolCall(
                        id=rtc.get("id", fn_name),
                        name=fn_name,
                        arguments=fn_args or {},
                    )
                )

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
            key_index_used=-1,  # diisi AIService
            token_usage=token_usage,
            latency_ms=latency_ms,
            tool_calls=tool_calls if tool_calls else None,
        )
