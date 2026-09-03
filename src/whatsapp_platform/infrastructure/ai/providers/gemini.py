"""Gemini LLM provider adapter.

Rate-limit signal:
- HTTP 429 with body JSON: error.details[] containing a RetryInfo entry with a
  retryDelay field (e.g. "13s" or "1.5s"). No standard Retry-After header.
- If retryDelay is absent or malformed, falls back to cooldown_default.
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

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"


def _parse_gemini_retry_delay(body: dict, default: float) -> float:
    """Parse retryDelay from Gemini 429 error body.

    Gemini returns retryDelay as a duration string like "13s" or "1.500s" inside
    error.details[].  We scan for the RetryInfo entry and parse the string.

    Returns the parsed seconds as float, or ``default`` on any failure (C2).
    """
    try:
        details = body.get("error", {}).get("details", [])
        for detail in details:
            if str(detail.get("@type", "")).endswith("RetryInfo"):
                delay_str: str = str(detail.get("retryDelay", ""))
                if delay_str:
                    numeric_part = delay_str.rstrip("sms ").rstrip(".")
                    return float(numeric_part)
    except Exception:
        pass
    return default


def _build_gemini_payload(
    messages: list[ProviderMessage],
    tools: list[ToolDefinition] | None = None,
) -> dict[str, Any]:
    """Convert ProviderMessage list and ToolDefinition list to Gemini REST API payload."""
    system_parts: list[dict[str, Any]] = []
    contents: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            system_parts.append({"text": msg.content})
        elif msg.role == "tool":
            # Function response returned to model
            try:
                resp_obj = json.loads(msg.content)
            except Exception:
                resp_obj = {"result": msg.content}

            part = {
                "functionResponse": {
                    "name": msg.name or msg.tool_call_id or "tool",
                    "response": resp_obj,
                }
            }
            contents.append({"role": "user", "parts": [part]})
        elif msg.role == "assistant":
            if msg.raw_parts:
                # Use exact raw parts from Gemini response to preserve thought_signature
                contents.append({"role": "model", "parts": msg.raw_parts})
            else:
                parts: list[dict[str, Any]] = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.raw_payload and isinstance(tc.raw_payload, dict):
                            parts.append(tc.raw_payload)
                        else:
                            parts.append({
                                "functionCall": {
                                    "name": tc.name,
                                    "args": tc.arguments,
                                }
                            })
                    if msg.content:
                        parts.insert(0, {"text": msg.content})
                elif msg.content:
                    parts.append({"text": msg.content})
                else:
                    parts.append({"text": ""})
                contents.append({"role": "model", "parts": parts})
        else:
            # user role
            contents.append({"role": "user", "parts": [{"text": msg.content}]})

    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}

    if tools:
        payload["tools"] = [
            {"function_declarations": [t.to_gemini_schema() for t in tools]}
        ]

    return payload


class GeminiProvider(ILLMProvider):
    """Adapter for Google Gemini REST API.

    Endpoint: POST {base}/{model}:generateContent?key={api_key}
    Request body: { "system_instruction": {...}, "contents": [...], "tools": [...] }
    """

    def __init__(self, client: httpx.AsyncClient, cooldown_default: float = 60.0) -> None:
        self._client = client
        self._cooldown_default = cooldown_default

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def supports_tool_calling(self) -> bool:
        return True

    async def generate(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Call Gemini generateContent endpoint without tools."""
        return await self._generate_internal(messages, api_key, model, tools=None)

    async def generate_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: list[ToolDefinition],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Call Gemini generateContent endpoint with function calling tools enabled."""
        return await self._generate_internal(messages, api_key, model, tools=tools)

    async def _generate_internal(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> AIResponse:
        payload = _build_gemini_payload(messages, tools=tools)

        url = f"{_GEMINI_API_BASE}/{model}:generateContent"
        params = {"key": api_key}

        start = time.monotonic()
        try:
            response = await self._client.post(url, json=payload, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Gemini request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Gemini network error: {exc}") from exc

        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code == 429:
            body = _safe_json(response)
            retry_after = _parse_gemini_retry_delay(body, self._cooldown_default)
            raise RateLimitError(
                f"Gemini rate limit (retry in {retry_after:.1f}s)", retry_after=retry_after
            )

        if not response.is_success:
            body = _safe_json(response)
            error_msg = body.get("error", {}).get("message", response.text[:200])
            raise ProviderError(
                f"Gemini error {response.status_code}: {error_msg}"
            )

        data = _safe_json(response)
        try:
            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Gemini unexpected response shape: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    ToolCall(
                        id=fc.get("name", ""),
                        name=fc.get("name", ""),
                        arguments=fc.get("args") or {},
                        raw_payload=part,
                    )
                )

        text_out = "".join(text_parts)

        # Extract token usage if available
        token_usage: dict[str, int] | None = None
        usage_meta = data.get("usageMetadata")
        if usage_meta:
            token_usage = {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            }

        return AIResponse(
            text=text_out,
            provider_used=self.provider_name,
            key_index_used=-1,
            token_usage=token_usage,
            latency_ms=latency_ms,
            tool_calls=tool_calls if tool_calls else None,
            raw_parts=parts if parts else None,
        )


def _safe_json(response: httpx.Response) -> dict:
    """Parse JSON body safely, returning empty dict on failure."""
    try:
        return response.json()
    except Exception:
        return {}

