"""Groq LLM provider adapter.

Rate-limit signal (C3 — researched from Groq API docs):
- HTTP 429 status code
- Retry-After HTTP header containing an integer number of seconds
- Also includes a human-readable message in the JSON body ("Please try again in Xs")
  but the header is the authoritative machine-readable signal

Fallback: if Retry-After header is absent or unparseable → cooldown_default.

Shared httpx.AsyncClient injected via constructor (C4).
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

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition

logger = structlog.get_logger()

_GROQ_API_BASE = "https://api.groq.com/openai/v1/chat/completions"


def _parse_groq_retry_after(response: httpx.Response, default: float) -> float:
    """Parse Retry-After header from Groq 429 response.

    Groq sends an integer number of seconds in the Retry-After header (C3).
    Falls back to default on any parse failure.
    """
    header = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except (ValueError, TypeError):
            pass
    return default


def _build_groq_messages(messages: list[ProviderMessage]) -> list[dict[str, Any]]:
    """Format ProviderMessage list to OpenAI-compatible messages."""
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
            result.append({"role": m.role, "content": m.content})
    return result


class GroqProvider(ILLMProvider):
    """Adapter for Groq OpenAI-compatible chat completions API."""

    def __init__(self, client: httpx.AsyncClient, cooldown_default: float = 60.0) -> None:
        self._client = client
        self._cooldown_default = cooldown_default

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def supports_tool_calling(self) -> bool:
        return True

    async def generate(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Call Groq chat completions endpoint without tools."""
        return await self._generate_internal(messages, api_key, model, tools=None)

    async def generate_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: list[ToolDefinition],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Call Groq chat completions endpoint with tools enabled."""
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
            "messages": _build_groq_messages(messages),
        }
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        try:
            response = await self._client.post(_GROQ_API_BASE, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Groq request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Groq network error: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code == 429:
            retry_after = _parse_groq_retry_after(response, self._cooldown_default)
            raise RateLimitError(
                f"Groq rate limit (retry in {retry_after:.1f}s)", retry_after=retry_after
            )

        if not response.is_success:
            body = _safe_json(response)
            error_msg = (
                body.get("error", {}).get("message", response.text[:200])
                if isinstance(body.get("error"), dict)
                else response.text[:200]
            )
            raise ProviderError(f"Groq error {response.status_code}: {error_msg}")

        data = _safe_json(response)
        try:
            choice = data["choices"][0]["message"]
            text = choice.get("content") or ""
            raw_tool_calls = choice.get("tool_calls")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Groq unexpected response shape: {exc}") from exc

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

        # Extract token usage
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
            tool_calls=tool_calls if tool_calls else None,
        )


def _safe_json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {}

