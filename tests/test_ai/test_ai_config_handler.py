"""Unit tests for AIChatCommandHandler (!ai commands)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.ai_config import AIChatCommandHandler
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy


def _make_ctx(text: str) -> CommandContext:
    cmd = BotCommand.parse(text, prefix="!")
    msg = Message(
        id="m101",
        chat_jid=JID.parse("628123456789@s.whatsapp.net"),
        sender_jid=JID.parse("628123456789@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
    )
    mock_send_uc = AsyncMock()
    mock_send_uc.execute = AsyncMock(return_value=msg)
    return CommandContext(command=cmd, message=msg, send_message_uc=mock_send_uc)


class DummyProvider:
    @property
    def provider_name(self):
        return "gemini"

    async def generate(self, messages, api_key, model):
        pass


@pytest.mark.asyncio
async def test_ai_command_on_sends_notice_first_time():
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    handler = AIChatCommandHandler(config_store, ai_service)

    ctx = _make_ctx("!ai on")
    await handler.handle(ctx)

    ctx.send_message_uc.execute.assert_awaited_once()
    reply = ctx.send_message_uc.execute.call_args[0][1]
    assert "Diaktifkan" in reply
    assert "Pemberitahuan Privasi" in reply  # first time notice sent!

    # Config should now be enabled
    config = await config_store.get("628123456789@s.whatsapp.net")
    assert config.enabled is True
    assert config.notice_sent is True


@pytest.mark.asyncio
async def test_ai_command_on_second_time_no_duplicate_notice():
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    handler = AIChatCommandHandler(config_store, ai_service)

    # Turn on 1st time
    await handler.handle(_make_ctx("!ai on"))

    # Turn on 2nd time
    ctx2 = _make_ctx("!ai on")
    await handler.handle(ctx2)
    reply2 = ctx2.send_message_uc.execute.call_args[0][1]
    assert "Pemberitahuan Privasi" not in reply2  # notice not duplicated!


@pytest.mark.asyncio
async def test_ai_command_off():
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    handler = AIChatCommandHandler(config_store, ai_service)

    await config_store.set_enabled("628123456789@s.whatsapp.net", True)
    ctx = _make_ctx("!ai off")
    await handler.handle(ctx)

    ctx.send_message_uc.execute.assert_awaited_once()
    reply = ctx.send_message_uc.execute.call_args[0][1]
    assert "Dinonaktifkan" in reply

    config = await config_store.get("628123456789@s.whatsapp.net")
    assert config.enabled is False


@pytest.mark.asyncio
async def test_ai_command_status():
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1", "k2"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    handler = AIChatCommandHandler(config_store, ai_service)

    ctx = _make_ctx("!ai status")
    await handler.handle(ctx)

    ctx.send_message_uc.execute.assert_awaited_once()
    reply = ctx.send_message_uc.execute.call_args[0][1]
    assert "STATUS AI CHAT" in reply
    assert "Gemini" in reply


@pytest.mark.asyncio
async def test_ai_command_reset_clears_context_cache():
    """C7 reset test: confirms clear_context is called."""
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    # Add dummy context
    await ai_service.append_to_context("628123456789@s.whatsapp.net", "user", "hello")
    assert len(await ai_service.get_context("628123456789@s.whatsapp.net")) == 1

    handler = AIChatCommandHandler(config_store, ai_service)
    ctx = _make_ctx("!ai reset")
    await handler.handle(ctx)

    # Context should now be empty!
    assert len(await ai_service.get_context("628123456789@s.whatsapp.net")) == 0


@pytest.mark.asyncio
async def test_ai_command_model_whitelist_validation():
    """C9 model whitelist test: rejects unknown model name with clear error."""
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    handler = AIChatCommandHandler(config_store, ai_service)

    # Invalid model name
    ctx_invalid = _make_ctx("!ai model gpt-999-turbo-ultra")
    await handler.handle(ctx_invalid)
    reply_invalid = ctx_invalid.send_message_uc.execute.call_args[0][1]
    assert "tidak didukung" in reply_invalid.lower() or "whitelist" in reply_invalid.lower()

    # Valid model name
    ctx_valid = _make_ctx("!ai model gemini-3.5-flash")
    await handler.handle(ctx_valid)
    reply_valid = ctx_valid.send_message_uc.execute.call_args[0][1]
    assert "diubah menjadi" in reply_valid.lower()

    config = await config_store.get("628123456789@s.whatsapp.net")
    assert config.model == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_ai_command_stats():
    config_store = AIChatConfigStore()
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
    )
    await ai_service.usage_counter.increment("gemini")
    handler = AIChatCommandHandler(config_store, ai_service)

    ctx = _make_ctx("!ai stats")
    await handler.handle(ctx)

    ctx.send_message_uc.execute.assert_awaited_once()
    reply = ctx.send_message_uc.execute.call_args[0][1]
    assert "STATISTIK PENGGUNAAN AI LLM" in reply
    assert "Gemini" in reply
