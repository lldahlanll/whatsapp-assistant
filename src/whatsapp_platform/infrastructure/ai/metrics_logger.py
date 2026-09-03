"""Token and LLM observability logging per request.

Emits structured 'AI_METRICS' logs detailing token usage, history sizes, prompt sizes,
and tool payload sizes WITHOUT logging raw message text or confidential data.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def log_ai_metrics(
    request_id: str,
    jid: str,
    intent: str,
    model: str,
    provider: str,
    history_message_count: int,
    history_chars: int,
    system_prompt_chars: int,
    tool_count: int,
    tool_definition_chars: int,
    tool_result_chars: int,
    token_usage: dict[str, int] | None,
    llm_call_number: int,
    total_llm_calls: int,
    latency_ms: float,
) -> None:
    """Emit structured AI_METRICS log entry for LLM request observability."""
    prompt_tokens = token_usage.get("prompt_tokens", 0) if token_usage else 0
    completion_tokens = token_usage.get("completion_tokens", 0) if token_usage else 0
    total_tokens = token_usage.get("total_tokens", 0) if token_usage else (prompt_tokens + completion_tokens)

    # Estimate input tokens if provider did not report prompt_tokens
    if prompt_tokens == 0:
        est_chars = history_chars + system_prompt_chars + tool_definition_chars + tool_result_chars
        prompt_tokens = max(1, est_chars // 4)
        total_tokens = prompt_tokens + completion_tokens

    logger.info(
        "AI_METRICS",
        request_id=request_id,
        jid=jid,
        intent=intent,
        model=model,
        provider=provider,
        history_message_count=history_message_count,
        history_chars=history_chars,
        system_prompt_chars=system_prompt_chars,
        tool_count=tool_count,
        tool_definition_chars=tool_definition_chars,
        tool_result_chars=tool_result_chars,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        total_tokens=total_tokens,
        llm_call_number=llm_call_number,
        total_llm_calls=total_llm_calls,
        latency_ms=round(latency_ms, 1),
    )
