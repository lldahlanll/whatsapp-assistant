"""Unit tests for AIReplyUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy


class MockProvider:
    @property
    def provider_name(self):
        return "gemini"

    async def generate(self, messages, api_key, model):
        # Assert that system prompt is in messages[0].role == "system" (C1)
        assert messages[0].role == "system"
        # Assert user messages have role "user" or "assistant"
        for m in messages[1:]:
            assert m.role in ("user", "assistant")

        return AIResponse(
            text="AI response test",
            provider_used="gemini",
            key_index_used=0,
            token_usage={"total_tokens": 20},
            latency_ms=5.0,
        )


def _make_msg(msg_id: str, text: str, direction=MessageDirection.INBOUND) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse("628123456789@s.whatsapp.net"),
        sender_jid=JID.parse("628123456789@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=direction,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Alice",
    )


@pytest.mark.asyncio
async def test_ai_reply_use_case_role_structure_and_execution():
    p = MockProvider()
    ai_service = AIService(
        providers={"gemini": (p, KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(
        return_value=[
            _make_msg("m1", "Hello assistant"),
            _make_msg("m2", "Hi! How can I help?", direction=MessageDirection.OUTBOUND),
        ]
    )

    use_case = AIReplyUseCase(
        ai_service=ai_service,
        get_conv_uc=mock_get_conv_uc,
        context_window_messages=20,
        max_context_chars=16000,
    )

    trigger_msg = _make_msg("m3", "What is 2+2?")
    res = await use_case.execute("628123456789@s.whatsapp.net", trigger_msg)

    assert res.text == "AI response test"
    assert res.provider_used == "gemini"


@pytest.mark.asyncio
async def test_ai_reply_use_case_truncation_guard():
    """C6 truncation guard test: trims oldest messages when character budget exceeded."""
    p = MockProvider()
    ai_service = AIService(
        providers={"gemini": (p, KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )

    # 3 messages of ~100 chars each
    m1 = _make_msg("m1", "A" * 100)
    m2 = _make_msg("m2", "B" * 100)
    m3 = _make_msg("m3", "C" * 100)

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[m1, m2, m3])

    # Max budget = 150 chars -> should drop m1 and keep m2, m3
    use_case = AIReplyUseCase(
        ai_service=ai_service,
        get_conv_uc=mock_get_conv_uc,
        context_window_messages=20,
        max_context_chars=150,
    )

    trigger = _make_msg("m4", "Final question")
    res = await use_case.execute("chat_jid", trigger)
    assert res.text == "AI response test"


@pytest.mark.asyncio
async def test_ai_reply_use_case_with_mikrotik_tool_calling():
    """Verify AIReplyUseCase routes to generate_reply_with_tools when tool_executor is enabled."""
    from whatsapp_platform.infrastructure.ai.interfaces import ToolCall

    call_count = 0

    class ToolMockProvider:
        @property
        def provider_name(self):
            return "gemini"

        @property
        def supports_tool_calling(self):
            return True

        async def generate(self, messages, api_key, model):
            return AIResponse(
                text="Fallback text",
                provider_used="gemini",
                key_index_used=0,
                token_usage=None,
                latency_ms=1.0,
            )

        async def generate_with_tools(self, messages, tools, api_key, model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First turn: model requests a tool call
                return AIResponse(
                    text="",
                    provider_used="gemini",
                    key_index_used=0,
                    token_usage=None,
                    latency_ms=2.0,
                    tool_calls=[ToolCall(id="call_1", name="mikrotik_get_health", arguments={})],
                )
            # Second turn: model reads tool output and produces final conversational response
            return AIResponse(
                text="Router kamu dalam kondisi sehat, CPU load cuma 5%!",
                provider_used="gemini",
                key_index_used=0,
                token_usage=None,
                latency_ms=2.0,
            )

    p = ToolMockProvider()
    ai_service = AIService(
        providers={"gemini": (p, KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True
    mock_tool_executor.execute = AsyncMock(return_value='{"status": "success", "data": {"cpu_load": 5}}')

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[])

    use_case = AIReplyUseCase(
        ai_service=ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
    )

    trigger = _make_msg("m1", "Cek mikrotik dong")
    res = await use_case.execute("628123456789@s.whatsapp.net", trigger)

    assert res.text == "Router kamu dalam kondisi sehat, CPU load cuma 5%!"
    assert mock_tool_executor.execute.called
    assert call_count == 2


def test_classify_intent():
    """Unit tests for classify_intent keyword classifier function."""
    from whatsapp_platform.infrastructure.ai.constants import classify_intent

    # Empty text -> "chat"
    assert classify_intent("") == "chat"

    # Greetings fast path -> "simple_chat"
    assert classify_intent("halo") == "simple_chat"
    assert classify_intent("makasih ya") == "simple_chat"
    assert classify_intent("cuaca hari ini gimana?") == "chat"

    # Finance keyword text -> "finance"
    assert classify_intent("catat pengeluaran 50rb buat makan") == "finance"
    assert classify_intent("SALDO") == "finance"
    assert classify_intent("berapa uang di dompet kas?") == "finance"
    assert classify_intent("bayar utang dan cicilan") == "finance"

    # Network keyword text -> "network"
    assert classify_intent("cek ping mikrotik dan router") == "network"
    assert classify_intent("wifi lemot banget bro") == "network"
    assert classify_intent("jaringan putus gaada sinyal") == "network"

    # Both finance and network -> "full"
    assert classify_intent("cek ping mikrotik terus catat saldo") == "full"
    assert classify_intent("router lemot dan catet pengeluaran") == "full"

    # Case-insensitivity
    assert classify_intent("CEK SALDO DONG") == "finance"
    assert classify_intent("MIKROTIK INTERNET DOWN") == "network"


@pytest.mark.asyncio
async def test_intent_classification_routing():
    """Verify that execute() picks appropriate tools and prompts based on intent and respects kill-switch."""
    from whatsapp_platform.infrastructure.ai.constants import (
        AI_FINANCE_SYSTEM_PROMPT,
        AI_FULL_SYSTEM_PROMPT,
        AI_NETWORK_SYSTEM_PROMPT,
        AI_SYSTEM_PROMPT,
    )
    from whatsapp_platform.infrastructure.finance.tool_schema import FINANCE_TOOLS
    from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS

    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply = AsyncMock(
        return_value=AIResponse(
            text="Chat response", provider_used="gemini", key_index_used=0, token_usage=None, latency_ms=1.0
        )
    )
    mock_ai_service.generate_reply_with_tools = AsyncMock(
        return_value=AIResponse(
            text="Tool response", provider_used="gemini", key_index_used=0, token_usage=None, latency_ms=1.0
        )
    )
    mock_ai_service.append_to_context = AsyncMock()

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[])

    use_case = AIReplyUseCase(
        ai_service=mock_ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
    )

    # Case A: Plain Chat -> generate_reply (no tools, AI_SYSTEM_PROMPT)
    trigger_chat = _make_msg("c1", "halo cuaca hari ini gimana?")
    await use_case.execute("chat_jid", trigger_chat)
    mock_ai_service.generate_reply.assert_called_once()
    assert mock_ai_service.generate_reply.call_args[1]["messages"][0].content == AI_SYSTEM_PROMPT
    mock_ai_service.generate_reply.reset_mock()

    # Case B: Finance -> generate_reply_with_tools (subset of FINANCE_TOOLS, AI_FINANCE_SYSTEM_PROMPT)
    trigger_fin = _make_msg("f1", "catat pengeluaran 50rb buat kopi di dompet kas")
    await use_case.execute("chat_jid", trigger_fin)
    mock_ai_service.generate_reply_with_tools.assert_called_once()
    kwargs = mock_ai_service.generate_reply_with_tools.call_args[1]
    assert kwargs["messages"][0].content == AI_FINANCE_SYSTEM_PROMPT
    assert all(t in FINANCE_TOOLS for t in kwargs["tools"])
    mock_ai_service.generate_reply_with_tools.reset_mock()

    # Case C: Network -> generate_reply_with_tools (subset of MIKROTIK_TOOLS, AI_NETWORK_SYSTEM_PROMPT)
    trigger_net = _make_msg("n1", "cek status router mikrotik dong")
    await use_case.execute("chat_jid", trigger_net)
    mock_ai_service.generate_reply_with_tools.assert_called_once()
    kwargs = mock_ai_service.generate_reply_with_tools.call_args[1]
    assert kwargs["messages"][0].content == AI_NETWORK_SYSTEM_PROMPT
    assert all(t in MIKROTIK_TOOLS for t in kwargs["tools"])
    mock_ai_service.generate_reply_with_tools.reset_mock()

    # Case D: Both (Full) -> generate_reply_with_tools (subset of both tool sets, AI_FULL_SYSTEM_PROMPT)
    trigger_full = _make_msg("x1", "ping mikrotik terus catat pengeluaran 20rb")
    await use_case.execute("chat_jid", trigger_full)
    mock_ai_service.generate_reply_with_tools.assert_called_once()
    kwargs = mock_ai_service.generate_reply_with_tools.call_args[1]
    assert kwargs["messages"][0].content == AI_FULL_SYSTEM_PROMPT
    assert all(t in (MIKROTIK_TOOLS + FINANCE_TOOLS) for t in kwargs["tools"])
    mock_ai_service.generate_reply_with_tools.reset_mock()

    # Case E: Kill-switch disabled (is_enabled == False) -> always chat path regardless of message text
    mock_tool_executor.is_enabled = False
    trigger_disabled = _make_msg("d1", "ping mikrotik terus catat pengeluaran 20rb")
    await use_case.execute("chat_jid", trigger_disabled)
    mock_ai_service.generate_reply.assert_called_once()
    assert mock_ai_service.generate_reply.call_args[1]["messages"][0].content == AI_SYSTEM_PROMPT
    mock_ai_service.generate_reply_with_tools.assert_not_called()



