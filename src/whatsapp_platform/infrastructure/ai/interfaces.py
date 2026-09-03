"""Antarmuka (interface) bersama dan tipe data standar untuk penyedia AI (Gemini, Groq, OpenRouter)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition


# ---------------------------------------------------------------------------
# Tipe Data
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """Tool/function call requested by LLM."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_payload: Any = None


@dataclass
class ProviderMessage:
    """Single message in the LLM conversation, using native API roles.

    Roles map directly to the provider API's role enum:
    - "system"    → bot instructions; never populated from user-controlled input
    - "user"      → inbound messages (human/group members)
    - "assistant" → previous bot replies
    - "tool"      → tool execution results returned to LLM
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    raw_parts: list[dict[str, Any]] | None = None


@dataclass
class AIResponse:
    """Consistent response envelope returned by AIService.generate_reply().

    All callers receive this shape regardless of which provider was used.
    token_usage is None when the provider does not report usage (e.g. free tiers).
    tool_calls is populated when LLM requests one or more tool executions.
    """

    text: str
    provider_used: str
    key_index_used: int
    token_usage: dict[str, int] | None
    latency_ms: float
    tool_calls: list[ToolCall] | None = None
    raw_parts: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RateLimitError(Exception):
    """Raised by a provider adapter when the API returns HTTP 429.

    retry_after is always a positive float (seconds).  Adapters must never
    set it to None or 0; use the configured cooldown default as fallback.
    """

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after: float = max(retry_after, 0.001)  # floor at 0.001s for safety


class ProviderError(Exception):
    """Raised by a provider adapter for any non-rate-limit failure.

    Includes: 4xx (bad request), 5xx (server error), network timeout,
    JSON parse failure, unexpected response shape.  These are NOT treated
    as rate-limit events — the key is NOT cooled down on this error.
    """


class AllProvidersExhaustedError(Exception):
    """Raised by AIService when every provider and every key is unavailable."""


# ---------------------------------------------------------------------------
# ILLMProvider interface
# ---------------------------------------------------------------------------


class ILLMProvider(ABC):
    """Abstract interface for a single LLM provider adapter.

    Each concrete adapter (Gemini, Groq, OpenRouter) implements this interface.
    The adapter owns:
    - Calling the provider HTTP API with the given key and model
    - Parsing rate-limit signals specific to that provider (C3 — per-provider parsing)
    - Raising RateLimitError or ProviderError with correct semantics

    The adapter does NOT own:
    - Key rotation (that's KeyPool)
    - Provider selection order (that's IProviderStrategy)
    - Retry loops (that's AIService)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier used in logs and stats (e.g. 'gemini')."""

    @property
    def supports_tool_calling(self) -> bool:
        """Indicate whether the provider supports native tool/function calling."""
        return False

    @abstractmethod
    async def generate(
        self,
        messages: list[ProviderMessage],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Generate a reply for the given conversation.

        Args:
            messages: Ordered conversation history with role separation.
            api_key:  The specific API key to use for this request.
            model:    The model name to invoke.

        Returns:
            AIResponse envelope on success.

        Raises:
            RateLimitError: On HTTP 429 with a populated retry_after.
            ProviderError:  On any other failure.
        """

    async def generate_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: list[ToolDefinition],
        api_key: str,
        model: str,
    ) -> AIResponse:
        """Generate a reply with tool definitions enabled.

        Default implementation falls back to standard generate().
        Providers supporting tool calling should override this method.
        """
        return await self.generate(messages, api_key, model)

