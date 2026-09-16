"""Layanan utama AI untuk mengelola kunci API, perputaran provider,
riwayat percakapan, dan pencatatan pemakaian harian.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.infrastructure.ai.compact_formatter import compact_tool_result
from whatsapp_platform.infrastructure.ai.constants import DEFAULT_MODELS
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    AllProvidersExhaustedError,
    ILLMProvider,
    ProviderError,
    ProviderMessage,
    RateLimitError,
)
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.metrics_logger import log_ai_metrics
from whatsapp_platform.infrastructure.ai.provider_strategy import IProviderStrategy
from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.ai.sqlite_store import AISQLiteStore

logger = structlog.get_logger()


class DailyUsageCounter:
    """Penghitung pemakaian AI harian untuk setiap provider."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def increment(self, provider: str) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        async with self._lock:
            self._counts[(provider, today)] += 1

    async def get_stats(self) -> dict[str, dict[str, int]]:
        """Mengembalikan statistik jumlah pemakaian per hari."""
        async with self._lock:
            result: dict[str, dict[str, int]] = defaultdict(dict)
            for (provider, date), count in self._counts.items():
                result[provider][date] = count
            return dict(result)


class _ProviderCircuitBreaker:
    """Pengaman otomatis untuk mengistirahatkan sementara provider yang semua kunci API-nya habis limit."""

    def __init__(self) -> None:
        self._cooling_until: dict[str, float] = {}

    def is_cooling(self, provider: str) -> bool:
        return time.monotonic() < self._cooling_until.get(provider, 0.0)

    def trip(self, provider: str, until: float) -> None:
        self._cooling_until[provider] = until

    def cooling_until(self, provider: str) -> float:
        return self._cooling_until.get(provider, 0.0)


class AIService:
    """Layanan utama pemproses balasan AI dan manajemen kunci API."""

    def __init__(
        self,
        providers: dict[str, tuple[ILLMProvider, KeyPool]],
        strategy: IProviderStrategy,
        default_models: dict[str, str] | None = None,
        db_store: AISQLiteStore | None = None,
        max_context_messages: int = 20,
    ) -> None:
        """
        Args:
            providers: {provider_name: (adapter, key_pool)}
            strategy:  Provider ordering strategy (e.g. FixedPriorityStrategy)
            default_models: {provider_name: default_model_name}
            db_store:  Optional SQLite store for persisting context history
            max_context_messages: Max messages per chat kept in context before trimming
        """
        self._providers = providers
        self._strategy = strategy
        self._default_models: dict[str, str] = default_models or DEFAULT_MODELS
        self._circuit_breaker = _ProviderCircuitBreaker()
        self.usage_counter = DailyUsageCounter()
        self._db_store = db_store
        self._max_context_messages = max_context_messages

        self._context_cache: dict[str, list[ProviderMessage]] = {}
        self._context_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Preload LLM context cache from SQLite into memory on startup."""
        if self._db_store:
            loaded = await self._db_store.load_all_context()
            async with self._context_lock:
                self._context_cache.update(loaded)

    # Context cache API
    # ------------------------------------------------------------------

    async def get_context(self, chat_jid: str) -> list[ProviderMessage]:
        """Return the current in-memory LLM context for a chat."""
        async with self._context_lock:
            return list(self._context_cache.get(chat_jid, []))

    async def append_to_context(
        self, chat_jid: str, role: str, content: str
    ) -> None:
        """Append a message to the context cache and persist to SQLite with trimming."""
        msg = ProviderMessage(role=role, content=content)  # type: ignore[arg-type]
        async with self._context_lock:
            if chat_jid not in self._context_cache:
                self._context_cache[chat_jid] = []
            self._context_cache[chat_jid].append(msg)
            self._trim_in_memory_context(chat_jid)

        if self._db_store:
            await self._db_store.append_context_message(chat_jid, msg)
            await self._db_store.trim_context_for_chat(chat_jid, self._max_context_messages)

    def _trim_in_memory_context(self, chat_jid: str) -> None:
        """Trim in-memory history keeping system message (if any) and N most recent messages."""
        ctx = self._context_cache.get(chat_jid, [])
        if len(ctx) <= self._max_context_messages:
            return

        if ctx and ctx[0].role == "system":
            system_msg = ctx[0]
            rest = ctx[1:]
            keep_count = max(0, self._max_context_messages - 1)
            self._context_cache[chat_jid] = [system_msg, *rest[-keep_count:]]

        else:
            self._context_cache[chat_jid] = ctx[-self._max_context_messages:]

    async def clear_context(self, chat_jid: str) -> None:
        """Clear the LLM context window for a chat (!ai reset).

        This clears the context used for LLM prompting in memory and SQLite.
        It does NOT delete any messages from the WhatsApp message database.
        """
        async with self._context_lock:
            self._context_cache.pop(chat_jid, None)
        if self._db_store:
            await self._db_store.delete_context_for_chat(chat_jid)
        logger.info("AI context cleared for chat", chat=chat_jid)


    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    async def _call_provider_with_retry(
        self,
        chat_jid: str,
        messages: list[ProviderMessage],
        model_override: str | None = None,
        tools: list[ToolDefinition] | None = None,
        intent: str = "chat",
        request_id: str = "",
        llm_call_number: int = 1,
        total_llm_calls: int = 1,
    ) -> AIResponse:
        """Helper to invoke the best provider and key with circuit breaker, rotation, and AI_METRICS logging."""
        available = {
            name: not self._circuit_breaker.is_cooling(name)
            for name in self._providers
        }
        ordered = self._strategy.ordered_providers(available)

        if not ordered:
            raise AllProvidersExhaustedError(
                "All providers are in cooldown — no provider available"
            )

        # Calculate payload metrics without logging raw messages
        system_chars = sum(len(m.content) for m in messages if m.role == "system")
        tool_result_chars = sum(len(m.content) for m in messages if m.role == "tool")
        non_system_non_tool = [m for m in messages if m.role in ("user", "assistant")]
        # History messages are non-system/non-tool messages excluding the last trigger message
        history_msgs = non_system_non_tool[:-1] if len(non_system_non_tool) > 1 else []
        history_chars = sum(len(m.content) for m in history_msgs)
        history_count = len(history_msgs)

        tool_count = len(tools) if tools else 0
        tool_def_chars = sum(len(json.dumps(t.to_openai_schema())) for t in tools) if tools else 0

        last_error: Exception | None = None

        for provider_name in ordered:
            adapter, pool = self._providers[provider_name]
            model = model_override or self._default_models.get(
                provider_name, DEFAULT_MODELS.get(provider_name, "")
            )

            for _attempt in range(pool.size()):
                key_info = await pool.next_available_key()
                if key_info is None:
                    until = await pool.all_cooling_until()
                    self._circuit_breaker.trip(provider_name, until)
                    logger.info(
                        "Provider circuit breaker tripped (all keys cooling)",
                        provider=provider_name,
                        cooling_until_in_seconds=max(0.0, until - time.monotonic()),
                    )
                    break

                idx, api_key = key_info
                call_start = time.monotonic()

                try:
                    if tools and adapter.supports_tool_calling:
                        response = await adapter.generate_with_tools(messages, tools, api_key, model)
                    else:
                        response = await adapter.generate(messages, api_key, model)

                    latency_ms = (time.monotonic() - call_start) * 1000
                    response.key_index_used = idx

                    # Log structured AI_METRICS without logging raw text
                    log_ai_metrics(
                        request_id=request_id or "req_" + str(int(call_start)),
                        jid=chat_jid,
                        intent=intent,
                        model=model,
                        provider=provider_name,
                        history_message_count=history_count,
                        history_chars=history_chars,
                        system_prompt_chars=system_chars,
                        tool_count=tool_count,
                        tool_definition_chars=tool_def_chars,
                        tool_result_chars=tool_result_chars,
                        token_usage=response.token_usage,
                        llm_call_number=llm_call_number,
                        total_llm_calls=total_llm_calls,
                        latency_ms=latency_ms,
                    )

                    await self.usage_counter.increment(provider_name)
                    return response

                except RateLimitError as exc:
                    latency_ms = (time.monotonic() - call_start) * 1000
                    await pool.mark_rate_limited(idx, exc.retry_after)
                    last_error = exc
                    logger.warning(
                        "llm_call_rate_limited",
                        provider=provider_name,
                        key_index=idx,
                        retry_after_seconds=exc.retry_after,
                        latency_ms=round(latency_ms, 1),
                        chat=chat_jid,
                    )

                except ProviderError as exc:
                    latency_ms = (time.monotonic() - call_start) * 1000
                    last_error = exc
                    logger.error(
                        "llm_call_provider_error",
                        provider=provider_name,
                        key_index=idx,
                        error=str(exc),
                        latency_ms=round(latency_ms, 1),
                        chat=chat_jid,
                        error_type="non_rate_limit",
                    )
                    break

            if await pool.is_all_cooling():
                until = await pool.all_cooling_until()
                self._circuit_breaker.trip(provider_name, until)

        raise AllProvidersExhaustedError(
            f"All providers exhausted. Last error: {last_error}"
        )

    async def generate_reply(
        self,
        chat_jid: str,
        messages: list[ProviderMessage],
        model_override: str | None = None,
        intent: str = "chat",
        request_id: str = "",
    ) -> AIResponse:
        """Generate a reply using the best available provider/key."""
        return await self._call_provider_with_retry(
            chat_jid=chat_jid,
            messages=messages,
            model_override=model_override,
            tools=None,
            intent=intent,
            request_id=request_id,
            llm_call_number=1,
            total_llm_calls=1,
        )

    async def generate_reply_with_tools(
        self,
        chat_jid: str,
        messages: list[ProviderMessage],
        tool_executor: Any,
        tools: list[ToolDefinition],
        user_jid: Any,
        wa_chat_jid: Any,
        model_override: str | None = None,
        max_tool_iterations: int = 3,
        max_tool_result_chars: int = 1000,
        intent: str = "chat",
        request_id: str = "",
    ) -> AIResponse:
        """Generate a reply running an agentic tool calling loop with the executor."""
        curr_messages = list(messages)
        iterations = 0

        while iterations < max_tool_iterations:
            response = await self._call_provider_with_retry(
                chat_jid=chat_jid,
                messages=curr_messages,
                model_override=model_override,
                tools=tools,
                intent=intent,
                request_id=request_id,
                llm_call_number=iterations + 1,
                total_llm_calls=iterations + 1,
            )

            # If LLM did not request any tool calls, return the final text response
            if not response.tool_calls:
                return response

            # LLM requested tool execution(s)
            logger.info(
                "LLM requested tool calls",
                chat=chat_jid,
                iteration=iterations + 1,
                tool_calls=[{"name": tc.name, "args": tc.arguments} for tc in response.tool_calls],
            )

            # Check for fast-path confirmation template (avoiding 2nd LLM call for simple mutations)
            if len(response.tool_calls) == 1:
                tc = response.tool_calls[0]
                tool_output = await tool_executor.execute(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    user_jid=user_jid,
                    chat_jid=wa_chat_jid,
                )
                is_group = bool(getattr(wa_chat_jid, "is_group", False))
                fast_path_reply = try_finance_mutation_fast_path(tc.name, tool_output, is_group=is_group)
                if fast_path_reply:
                    logger.info(
                        "Finance mutation fast-path confirmation generated locally (skipped 2nd LLM call)",
                        chat=chat_jid,
                        tool=tc.name,
                    )
                    return AIResponse(
                        text=fast_path_reply,
                        provider_used=response.provider_used,
                        key_index_used=response.key_index_used,
                        token_usage=response.token_usage,
                        latency_ms=response.latency_ms,
                    )

                # Not fast-path, append compacted result
                compacted_output = compact_tool_result(tc.name, tool_output, max_chars=max_tool_result_chars)
                curr_messages.append(
                    ProviderMessage(
                        role="assistant",
                        content=response.text or "",
                        tool_calls=response.tool_calls,
                        raw_parts=response.raw_parts,
                    )
                )
                curr_messages.append(
                    ProviderMessage(
                        role="tool",
                        content=compacted_output,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
            else:
                # Multiple tool calls requested
                curr_messages.append(
                    ProviderMessage(
                        role="assistant",
                        content=response.text or "",
                        tool_calls=response.tool_calls,
                        raw_parts=response.raw_parts,
                    )
                )
                for tc in response.tool_calls:
                    tool_output = await tool_executor.execute(
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        user_jid=user_jid,
                        chat_jid=wa_chat_jid,
                    )
                    compacted_output = compact_tool_result(tc.name, tool_output, max_chars=max_tool_result_chars)
                    curr_messages.append(
                        ProviderMessage(
                            role="tool",
                            content=compacted_output,
                            tool_call_id=tc.id,
                            name=tc.name,
                        )
                    )

            iterations += 1

        # Fallback if max iterations exceeded: ask LLM for final response without tools
        logger.warning(
            "Max tool calling iterations reached, forcing final text response",
            chat=chat_jid,
            iterations=iterations,
        )
        return await self._call_provider_with_retry(
            chat_jid=chat_jid,
            messages=curr_messages,
            model_override=model_override,
            tools=None,
            intent=intent,
            request_id=request_id,
            llm_call_number=iterations + 1,
            total_llm_calls=iterations + 1,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def get_provider_status(self) -> dict[str, dict]:
        """Return current status for all providers — used by !ai stats and !ai status."""
        status = {}
        for name, (_, pool) in self._providers.items():
            cooling_keys = await pool.get_cooling_keys()
            circuit_breaker_cooling = self._circuit_breaker.is_cooling(name)
            status[name] = {
                "available_keys": pool.size() - len(cooling_keys),
                "total_keys": pool.size(),
                "cooling_keys": cooling_keys,
                "circuit_breaker_active": circuit_breaker_cooling,
                "circuit_breaker_until": (
                    self._circuit_breaker.cooling_until(name)
                    if circuit_breaker_cooling
                    else None
                ),
            }
        return status
