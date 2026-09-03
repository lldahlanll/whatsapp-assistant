"""Tests for P0 Token Optimization (Step 6).

Verifies:
1. Fast path greeting ("hallo" / "hai" / "hello") -> intent simple_chat/chat, history=0, tools=0, llm_calls=1
2. General prompt ("kamu siapa?") -> history <= 3, tools=0, llm_calls=1
3. Balance query ("saldo BCA saya berapa?") -> only balance-related tools sent
4. Resource query ("CPU MikroTik saya berapa?") -> only system-resource tools sent
"""

from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse
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


@pytest.mark.asyncio
async def test_p0_scenario_1_fast_path_greeting():
    """"hallo" / "hai" / "hello" -> intent simple_chat/chat, history=0, tools=0, llm_calls=1."""
    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply = AsyncMock(
        return_value=AIResponse(text="Halo! Ada yang bisa Nara bantu?", provider_used="gemini", key_index_used=0, token_usage={"prompt_tokens": 80, "completion_tokens": 15, "total_tokens": 95}, latency_ms=10.0)
    )
    mock_ai_service.append_to_context = AsyncMock()

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[_make_msg("h1", "past message 1"), _make_msg("h2", "past message 2")])

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True

    settings = Settings(ai_chat_history_limit=3)
    use_case = AIReplyUseCase(
        ai_service=mock_ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
        settings=settings,
    )

    trigger = _make_msg("m1", "hallo")
    res = await use_case.execute("628123456789@s.whatsapp.net", trigger)

    # 1. DB history must NOT be queried for simple_chat fast path (history=0)
    mock_get_conv_uc.execute.assert_not_called()
    mock_ai_service.generate_reply.assert_called_once()

    kwargs = mock_ai_service.generate_reply.call_args[1]
    assert kwargs["intent"] == "simple_chat"
    messages = kwargs["messages"]
    # Only System message + User message (no history)
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert res.text == "Halo! Ada yang bisa Nara bantu?"


@pytest.mark.asyncio
async def test_p0_scenario_2_role_query():
    """"bagaimana cara kerja AI ini?" -> history <= 3, tools=0, llm_calls=1."""
    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply = AsyncMock(
        return_value=AIResponse(text="Saya Nara, asisten AI Anda.", provider_used="gemini", key_index_used=0, token_usage={"prompt_tokens": 120, "completion_tokens": 10, "total_tokens": 130}, latency_ms=12.0)
    )
    mock_ai_service.append_to_context = AsyncMock()

    past_messages = [_make_msg(f"h{i}", f"old msg {i}") for i in range(10)]
    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=past_messages[:3])

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True

    settings = Settings(ai_chat_history_limit=3)
    use_case = AIReplyUseCase(
        ai_service=mock_ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
        settings=settings,
    )

    trigger = _make_msg("m2", "bagaimana cara kerja AI ini?")
    await use_case.execute("628123456789@s.whatsapp.net", trigger)

    # get_conv_uc should be called with limit=3 (not 20!)
    mock_get_conv_uc.execute.assert_called_once_with("628123456789@s.whatsapp.net", limit=3)
    mock_ai_service.generate_reply.assert_called_once()

    kwargs = mock_ai_service.generate_reply.call_args[1]
    assert kwargs["intent"] == "chat"


@pytest.mark.asyncio
async def test_p0_scenario_3_balance_query():
    """"saldo BCA saya berapa?" -> only balance-related tools sent."""
    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply_with_tools = AsyncMock(
        return_value=AIResponse(text="Saldo BCA Anda Rp 5.000.000.", provider_used="gemini", key_index_used=0, token_usage={"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320}, latency_ms=25.0)
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

    trigger = _make_msg("m3", "saldo BCA saya berapa?")
    await use_case.execute("628123456789@s.whatsapp.net", trigger)

    mock_get_conv_uc.execute.assert_called_once_with("628123456789@s.whatsapp.net", limit=5)
    mock_ai_service.generate_reply_with_tools.assert_called_once()

    kwargs = mock_ai_service.generate_reply_with_tools.call_args[1]
    assert kwargs["intent"] == "finance"
    sent_tools = kwargs["tools"]

    # Verify ONLY finance_get_balance tool is sent (1 tool instead of 8)
    assert len(sent_tools) == 1
    assert sent_tools[0].name == "finance_get_balance"


@pytest.mark.asyncio
async def test_p0_scenario_4_cpu_mikrotik_query():
    """"CPU MikroTik saya berapa?" -> only system-resource tools sent."""
    mock_ai_service = AsyncMock()
    mock_ai_service.generate_reply_with_tools = AsyncMock(
        return_value=AIResponse(text="Penggunaan CPU MikroTik 12%.", provider_used="gemini", key_index_used=0, token_usage={"prompt_tokens": 250, "completion_tokens": 15, "total_tokens": 265}, latency_ms=30.0)
    )
    mock_ai_service.append_to_context = AsyncMock()

    mock_get_conv_uc = AsyncMock()
    mock_get_conv_uc.execute = AsyncMock(return_value=[])

    mock_tool_executor = AsyncMock()
    mock_tool_executor.is_enabled = True

    settings = Settings(ai_network_history_limit=3)
    use_case = AIReplyUseCase(
        ai_service=mock_ai_service,
        get_conv_uc=mock_get_conv_uc,
        tool_executor=mock_tool_executor,
        settings=settings,
    )

    trigger = _make_msg("m4", "CPU MikroTik saya berapa?")
    await use_case.execute("628123456789@s.whatsapp.net", trigger)

    mock_get_conv_uc.execute.assert_called_once_with("628123456789@s.whatsapp.net", limit=3)
    mock_ai_service.generate_reply_with_tools.assert_called_once()

    kwargs = mock_ai_service.generate_reply_with_tools.call_args[1]
    assert kwargs["intent"] == "network"
    sent_tools = kwargs["tools"]

    # Verify ONLY mikrotik_get_health tool is sent (1 tool instead of 8)
    tool_names = [t.name for t in sent_tools]
    assert "mikrotik_get_health" in tool_names
    assert "mikrotik_get_firewall" not in tool_names
    assert "mikrotik_get_dhcp_leases" not in tool_names
