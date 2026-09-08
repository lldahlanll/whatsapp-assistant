"""Tests for P1 Token Optimization (Step 8).

Verifies:
1. Finance mutation fast path ("catat beli makan 25rb pakai BCA") -> local template response, no 2nd LLM call.
2. Compact tool result & MAX_TOOL_RESULT_CHARS protection.
3. MAX_TOOL_ITERATIONS enforcement for multi-iteration agentic loop.
"""

import json
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.ai.compact_formatter import compact_tool_result
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse, ToolCall
from whatsapp_platform.infrastructure.config.settings import Settings


def _make_msg(msg_id: str, text: str) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse("628123456789@s.whatsapp.net"),
        sender_jid=JID.parse("628123456789@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        push_name="Tester",
        is_from_me=False,
    )


def test_compact_formatter_truncates_large_payload():
    """Verify that compact_tool_result enforces max_chars truncation limit."""
    large_log_output = json.dumps({"status": "ok", "logs": [{"event": f"log entry {i}" * 10} for i in range(50)]})
    compacted = compact_tool_result("mikrotik_get_logs", large_log_output, max_chars=200)
    assert len(compacted) <= 200
    assert "[truncated]" in compacted


def test_finance_mutation_fast_path_generator():
    """Verify local confirmation template generation for successful mutation."""
    raw_res = json.dumps({
        "status": "success",
        "transaction": {
            "amount": 25000,
            "category_name": "Makanan & Minuman",
            "account_name": "BCA",
            "description": "beli makan 25rb"
        },
        "new_balance": 4975000
    })
    confirmation = try_finance_mutation_fast_path("finance_add_expense", raw_res)
    assert confirmation is not None
    assert "Pengeluaran Dicatat" in confirmation
    assert "Rp 25.000" in confirmation
    assert "BCA" in confirmation
    assert "Rp 4.975.000" in confirmation


def test_finance_query_fast_path_get_transactions():
    """Verify finance_get_transactions fast path formatting."""
    raw_res = json.dumps({
        "status": "success",
        "count": 2,
        "transactions": [
            {
                "transaction_id": "TX01",
                "date": "2026-09-03",
                "type": "expense",
                "amount": 50000,
                "description": "Makan siang",
                "account": "BCA",
            },
            {
                "transaction_id": "TX02",
                "date": "2026-09-02",
                "type": "income",
                "amount": 1000000,
                "description": "Gaji",
                "account": "Mandiri",
            }
        ]
    })
    result = try_finance_mutation_fast_path("finance_get_transactions", raw_res)
    assert result is not None
    assert "Riwayat Transaksi" in result
    assert "Rp 50.000" in result
    assert "Rp 1.000.000" in result
    assert "TX01" in result


def test_finance_query_fast_path_get_balance():
    """Verify finance_get_balance fast path formatting."""
    raw_res = json.dumps({
        "status": "success",
        "accounts": [
            {"name": "BCA", "type": "bank", "balance": 1500000},
            {"name": "Kas", "type": "cash", "balance": 250000}
        ]
    })
    result = try_finance_mutation_fast_path("finance_get_balance", raw_res)
    assert result is not None
    assert "Saldo Rekening" in result
    assert "Rp 1.500.000" in result
    assert "Rp 1.750.000" in result


def test_finance_query_fast_path_delete_account_confirmation():
    """Verify finance_delete_account need_confirmation fast path."""
    raw_res = json.dumps({
        "status": "need_confirmation",
        "account_name": "BCA",
        "account_type": "bank",
        "balance": 1500000
    })
    result = try_finance_mutation_fast_path("finance_delete_account", raw_res)
    assert result is not None
    assert "Konfirmasi Hapus Rekening" in result
    assert "BCA" in result
    assert "Rp 1.500.000" in result


@pytest.mark.asyncio
async def test_p1_scenario_finance_mutation_fast_path():
    """"catat beli makan 25rb pakai BCA" -> fast path confirmation without 2nd LLM call."""
    tool_call = ToolCall(
        id="tc1",
        name="finance_add_expense",
        arguments={"amount": 25000, "description": "beli makan 25rb", "account_name": "BCA"}
    )
    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply_with_tools = AsyncMock(
        return_value=AIResponse(text="✅ *Pengeluaran Dicatat*\n\n• Jumlah: Rp 25.000\n• Rekening: BCA", provider_used="gemini", key_index_used=0, token_usage={"prompt_tokens": 150, "completion_tokens": 10, "total_tokens": 160}, latency_ms=20.0)
    )
    mock_ai_service.append_to_context = AsyncMock()

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[])

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True

    settings = Settings(ai_finance_history_limit=5)
    use_case = AIReplyUseCase(
        ai_service=mock_ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
        settings=settings,
    )

    trigger = _make_msg("m_fin1", "catat beli makan 25rb pakai BCA")
    res = await use_case.execute("628123456789@s.whatsapp.net", trigger)

    assert "Pengeluaran Dicatat" in res.text
    mock_ai_service.generate_reply_with_tools.assert_called_once()


@pytest.mark.asyncio
async def test_p1_scenario_max_tool_iterations_enforced():
    """Verify MAX_TOOL_ITERATIONS (default 3) stops infinite tool loops."""
    from whatsapp_platform.infrastructure.ai.ai_service import AIService

    mock_provider = AsyncMock()
    # Provider always returns tool_calls (simulating infinite tool loop)
    mock_provider.generate_with_tools = AsyncMock(
        return_value=AIResponse(
            text="",
            provider_used="gemini",
            key_index_used=0,
            token_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            latency_ms=15.0,
            tool_calls=[ToolCall(id="tc1", name="mikrotik_get_traffic", arguments={})],
        )
    )
    mock_provider.generate = AsyncMock(
        return_value=AIResponse(
            text="Forced final text response after max iterations",
            provider_used="gemini",
            key_index_used=0,
            token_usage={"prompt_tokens": 150, "completion_tokens": 10, "total_tokens": 160},
            latency_ms=15.0,
        )
    )
    mock_provider.provider_name = "gemini"
    mock_provider.supports_tool_calling = True

    mock_key_pool = AsyncMock()
    mock_key_pool.size = lambda: 1
    mock_key_pool.next_available_key = AsyncMock(return_value=(0, "fake-key"))
    mock_key_pool.is_all_cooling = AsyncMock(return_value=False)

    mock_strategy = AsyncMock()
    mock_strategy.ordered_providers = lambda avail: ["gemini"]

    ai_service = AIService(
        providers={"gemini": (mock_provider, mock_key_pool)},
        strategy=mock_strategy,
    )

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value=json.dumps({"status": "ok", "traffic": "10Mbps"}))

    from whatsapp_platform.infrastructure.ai.interfaces import ProviderMessage
    messages = [ProviderMessage(role="system", content="sys prompt"), ProviderMessage(role="user", content="kenapa internet lambat?")]

    from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS
    res = await ai_service.generate_reply_with_tools(
        chat_jid="628123456789@s.whatsapp.net",
        messages=messages,
        tool_executor=mock_executor,
        tools=[MIKROTIK_TOOLS[0]],
        user_jid=None,
        wa_chat_jid=None,
        max_tool_iterations=3,
    )

    # Must invoke tool loop at most 3 times, then fall back to generate without tools
    assert mock_provider.generate_with_tools.call_count == 3
    assert mock_provider.generate.call_count == 1
    assert "Forced final text response" in res.text
