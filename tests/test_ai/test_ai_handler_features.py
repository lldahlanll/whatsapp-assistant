"""Unit tests for AIMessageHandler: idempotency, fallback messaging, and group mention/reply."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.handler import AIMessageHandler
from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.infrastructure.ai.constants import (
    AI_FALLBACK_BUSY_MESSAGE,
    AI_FALLBACK_ERROR_MESSAGE,
)
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    AllProvidersExhaustedError,
    ProviderError,
)
from whatsapp_platform.infrastructure.config.settings import Settings


def _make_event(
    msg_id: str,
    text: str,
    chat_jid: str = "628123456789@s.whatsapp.net",
    reply_to_id: str | None = None,
    quoted_sender_jid: JID | None = None,
) -> MessageReceived:
    msg = Message(
        id=msg_id,
        chat_jid=JID.parse(chat_jid),
        sender_jid=JID.parse("628111111111@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        is_from_me=False,
        reply_to_id=reply_to_id,
        quoted_sender_jid=quoted_sender_jid,
    )
    return MessageReceived(message=msg)


@pytest.mark.asyncio
async def test_handler_idempotency_prevents_duplicate_processing():
    """P2: Event with identical message_id is ignored on second arrival."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Halo balasan AI",
            provider_used="gemini",
            key_index_used=0,
            token_usage=None,
            latency_ms=10.0,
        )
    )
    mock_send_msg_uc = AsyncMock()
    config_store = AIChatConfigStore()
    chat_jid = "628123456789@s.whatsapp.net"
    await config_store.set_enabled(chat_jid, True)

    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    event1 = _make_event(msg_id="msg_duplicate_1", text="Hai bot")

    # Send first time -> should process
    await handler.on_message_received(event1)
    assert mock_ai_reply_uc.execute.call_count == 1
    assert mock_send_msg_uc.execute.call_count == 1

    # Send second time with identical message_id -> should be skipped!
    await handler.on_message_received(event1)
    assert mock_ai_reply_uc.execute.call_count == 1
    assert mock_send_msg_uc.execute.call_count == 1

    # Send message with NEW message_id -> should process normally
    event2 = _make_event(msg_id="msg_new_2", text="Hai lagi bot")
    await handler.on_message_received(event2)
    assert mock_ai_reply_uc.execute.call_count == 2
    assert mock_send_msg_uc.execute.call_count == 2


@pytest.mark.asyncio
async def test_handler_fallback_on_all_providers_exhausted():
    """P3: AllProvidersExhaustedError triggers busy fallback message to user."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(side_effect=AllProvidersExhaustedError("All exhausted"))
    mock_send_msg_uc = AsyncMock()
    config_store = AIChatConfigStore()
    chat_jid = "628123456789@s.whatsapp.net"
    await config_store.set_enabled(chat_jid, True)

    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    event = _make_event(msg_id="msg_exhausted_1", text="Tolong bantu saya")
    await handler.on_message_received(event)

    # Fallback busy message should be sent to user
    mock_send_msg_uc.execute.assert_awaited_once_with(
        chat_jid, AI_FALLBACK_BUSY_MESSAGE, quoted=None
    )


@pytest.mark.asyncio
async def test_handler_fallback_on_unexpected_exception():
    """P3: General unexpected exception triggers generic error fallback message."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(side_effect=ProviderError("Connection failed 500"))
    mock_send_msg_uc = AsyncMock()
    config_store = AIChatConfigStore()
    chat_jid = "628123456789@s.whatsapp.net"
    await config_store.set_enabled(chat_jid, True)

    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    event = _make_event(msg_id="msg_error_1", text="Tes error")
    await handler.on_message_received(event)

    # Fallback error message should be sent to user
    mock_send_msg_uc.execute.assert_awaited_once_with(
        chat_jid, AI_FALLBACK_ERROR_MESSAGE, quoted=None
    )


@pytest.mark.asyncio
async def test_handler_fallback_send_failure_handled_gracefully():
    """P3: Failure in SendMessageUseCase during fallback does not crash handler."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(side_effect=AllProvidersExhaustedError("All exhausted"))
    mock_send_msg_uc = AsyncMock()
    mock_send_msg_uc.execute = AsyncMock(side_effect=RuntimeError("Gateway network down"))
    config_store = AIChatConfigStore()
    chat_jid = "628123456789@s.whatsapp.net"
    await config_store.set_enabled(chat_jid, True)

    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    event = _make_event(msg_id="msg_send_fail_1", text="Tes crash")
    # Should not raise exception
    await handler.on_message_received(event)


@pytest.mark.asyncio
async def test_personal_chat_connects_directly_to_ai():
    """Personal chat DM automatically connects to AI without explicit !ai on command."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Halo dari AI!",
            provider_used="gemini",
            key_index_used=0,
            token_usage=None,
            latency_ms=5.0,
        )
    )
    mock_send_msg_uc = AsyncMock()
    config_store = AIChatConfigStore()
    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    # Personal chat event (no mention, no prior config setup)
    event = _make_event(msg_id="pc_msg_1", text="Hello AI assistant", chat_jid="628123456789@s.whatsapp.net")
    await handler.on_message_received(event)

    # Should process directly!
    mock_ai_reply_uc.execute.assert_awaited_once()
    mock_send_msg_uc.execute.assert_awaited_once_with("628123456789@s.whatsapp.net", "Halo dari AI!", quoted=None)


@pytest.mark.asyncio
async def test_group_chat_requires_mention_or_reply_to_bot():
    """Group chat skips unmentioned messages, but replies when mentioned OR replying to bot."""
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Halo grup!",
            provider_used="gemini",
            key_index_used=0,
            token_usage=None,
            latency_ms=5.0,
        )
    )
    mock_send_msg_uc = AsyncMock()
    mock_repo = AsyncMock()

    group_jid = "120363000123456789@g.us"
    config_store = AIChatConfigStore()
    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings(ai_bot_mention_name="Nara")

    # Mock quoted message from bot
    quoted_bot_msg = Message(
        id="bot_msg_99",
        chat_jid=JID.parse(group_jid),
        sender_jid=JID.parse("me@s.whatsapp.net"),
        content=TextContent(text="Saya bot Nara"),
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        timestamp=datetime.now(UTC),
        is_from_me=True,
    )

    # Mock quoted message from normal user
    quoted_user_msg = Message(
        id="user_msg_88",
        chat_jid=JID.parse(group_jid),
        sender_jid=JID.parse("628111111111@s.whatsapp.net"),
        content=TextContent(text="Halo teman2"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        is_from_me=False,
    )

    async def get_by_id_side_effect(msg_id: str):
        if msg_id == "bot_msg_99":
            return quoted_bot_msg
        if msg_id == "user_msg_88":
            return quoted_user_msg
        return None

    mock_repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
        message_repo=mock_repo,
    )

    # 1. Normal group message without mention or reply -> SKIPPED
    event1 = _make_event(msg_id="g_1", text="Kapan kumpul guys?", chat_jid=group_jid)
    await handler.on_message_received(event1)
    assert mock_ai_reply_uc.execute.call_count == 0

    # 2. Group message mentioning @Nara -> PROCESSED
    event2 = _make_event(msg_id="g_2", text="@Nara tolong bantu", chat_jid=group_jid)
    await handler.on_message_received(event2)
    assert mock_ai_reply_uc.execute.call_count == 1

    # 3. Group message replying to a normal user's message -> SKIPPED
    event3 = _make_event(
        msg_id="g_3", text="Bener tuh", chat_jid=group_jid, reply_to_id="user_msg_88"
    )
    await handler.on_message_received(event3)
    assert mock_ai_reply_uc.execute.call_count == 1

    # 4. Group message replying to BOT's message -> PROCESSED
    event4 = _make_event(
        msg_id="g_4", text="Jelaskan lagi dong", chat_jid=group_jid, reply_to_id="bot_msg_99"
    )
    await handler.on_message_received(event4)
    assert mock_ai_reply_uc.execute.call_count == 2


@pytest.mark.asyncio
async def test_flow_rules_private_and_group():
    """Verify flow rules:
    - PRIVATE CHAT: User -> Bot => Bot sends normal message (quoted=None)
    - GROUP: User mention bot => Bot replies to user message (quoted="g_mention")
    - GROUP: User reply bot => Bot replies to user message (quoted="g_reply")
    - GROUP: User no mention & no reply => Bot stays silent (diam)
    """
    mock_ai_reply_uc = AsyncMock()
    mock_ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Jawaban bot",
            provider_used="gemini",
            key_index_used=0,
            token_usage=None,
            latency_ms=5.0,
        )
    )
    mock_send_msg_uc = AsyncMock()
    mock_repo = AsyncMock()

    group_jid = "120363000999999999@g.us"
    private_jid = "628999888777@s.whatsapp.net"
    config_store = AIChatConfigStore()
    await config_store.set_enabled(group_jid, True)
    await config_store.set_enabled(private_jid, True)
    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings(ai_bot_mention_name="Nara")

    bot_msg = Message(
        id="bot_msg_1",
        chat_jid=JID.parse(group_jid),
        sender_jid=JID.parse("me@s.whatsapp.net"),
        content=TextContent(text="Halo"),
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        timestamp=datetime.now(UTC),
        is_from_me=True,
    )
    mock_repo.get_by_id = AsyncMock(return_value=bot_msg)

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
        message_repo=mock_repo,
    )

    # 1. PRIVATE CHAT: User -> Bot => Bot -> normal message (quoted=None)
    ev_priv = _make_event(msg_id="priv_1", text="Halo bot", chat_jid=private_jid)
    await handler.on_message_received(ev_priv)
    mock_send_msg_uc.execute.assert_awaited_with(private_jid, "Jawaban bot", quoted=None)

    # 2. GROUP: User mention bot => Bot -> reply ke pesan user (quoted="g_mention")
    ev_mention = _make_event(msg_id="g_mention", text="@Nara halo", chat_jid=group_jid)
    await handler.on_message_received(ev_mention)
    mock_send_msg_uc.execute.assert_awaited_with(group_jid, "Jawaban bot", quoted="g_mention")

    # 3. GROUP: User reply bot => Bot -> reply ke pesan user (quoted="g_reply")
    ev_reply = _make_event(
        msg_id="g_reply", text="Ada apa?", chat_jid=group_jid, reply_to_id="bot_msg_1"
    )
    await handler.on_message_received(ev_reply)
    mock_send_msg_uc.execute.assert_awaited_with(group_jid, "Jawaban bot", quoted="g_reply")

    # 4. GROUP: User tidak mention & bukan reply bot => Bot diam
    mock_send_msg_uc.execute.reset_mock()
    ev_silent = _make_event(msg_id="g_silent", text="Random chat", chat_jid=group_jid)
    await handler.on_message_received(ev_silent)
    mock_send_msg_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_typing_indicator_lifecycle_success_and_failure():
    """Verify Typing ON happens before LLM, and Typing OFF runs in finally block on both success and error."""
    mock_gateway = AsyncMock()
    mock_ai_reply_uc = AsyncMock()
    mock_send_msg_uc = AsyncMock()
    config_store = AIChatConfigStore()
    chat_jid = "628123456789@s.whatsapp.net"
    await config_store.set_enabled(chat_jid, True)
    rate_guard = PerChatRateGuard(max_requests=10, window_seconds=60.0)
    settings = Settings()

    # Success case: AI succeeds
    mock_ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Halo",
            provider_used="gemini",
            key_index_used=0,
            token_usage=None,
            latency_ms=5.0,
        )
    )
    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=config_store,
        rate_guard=rate_guard,
        settings=settings,
        gateway=mock_gateway,
    )

    ev1 = _make_event(msg_id="t_1", text="Hai", chat_jid=chat_jid)
    await handler.on_message_received(ev1)

    # Typing ON (composing=True) then Typing OFF (composing=False)
    assert mock_gateway.send_chat_presence.call_count == 2
    calls = mock_gateway.send_chat_presence.call_args_list
    assert calls[0].kwargs == {"composing": True}
    assert calls[1].kwargs == {"composing": False}

    # Error case: LLM raises exception -> Typing OFF still called in finally block!
    mock_gateway.send_chat_presence.reset_mock()
    mock_ai_reply_uc.execute = AsyncMock(side_effect=AllProvidersExhaustedError("All down"))

    ev2 = _make_event(msg_id="t_2", text="Hai error", chat_jid=chat_jid)
    await handler.on_message_received(ev2)

    assert mock_gateway.send_chat_presence.call_count == 2
    calls_err = mock_gateway.send_chat_presence.call_args_list
    assert calls_err[0].kwargs == {"composing": True}
    assert calls_err[1].kwargs == {"composing": False}


@pytest.mark.asyncio
async def test_ai_handler_skips_customer_lookup_phone_number_message():
    """Verify AIMessageHandler skips AI reply when message contains a phone number for Customer Lookup."""
    mock_ai_reply_uc = AsyncMock()
    mock_send_msg_uc = AsyncMock()
    mock_config_store = AsyncMock(spec=AIChatConfigStore)

    cfg = AsyncMock()
    cfg.enabled = True
    cfg.model = None
    mock_config_store.get.return_value = cfg

    rate_guard = PerChatRateGuard()
    settings = Settings()

    handler = AIMessageHandler(
        ai_reply_uc=mock_ai_reply_uc,
        send_msg_uc=mock_send_msg_uc,
        config_store=mock_config_store,
        rate_guard=rate_guard,
        settings=settings,
    )

    ev = _make_event(msg_id="phone_1", text="Cek 08123456789 min", chat_jid="628123456789@s.whatsapp.net")
    await handler.on_message_received(ev)

    mock_ai_reply_uc.execute.assert_not_called()
    mock_send_msg_uc.execute.assert_not_called()



