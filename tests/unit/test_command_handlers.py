"""Unit tests for built-in command handlers (PingHandler, HelpHandler)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.help import HelpHandler
from whatsapp_platform.features.commands.handlers.ping import PingHandler


def _make_ctx(text: str = "!ping") -> CommandContext:
    cmd = BotCommand.parse(text, prefix="!")
    msg = Message(
        id="msg-001",
        chat_jid=JID.parse("628111111@s.whatsapp.net"),
        sender_jid=JID.parse("628222222@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
    )
    mock_send_uc = AsyncMock()
    mock_send_uc.execute = AsyncMock(return_value=msg)
    return CommandContext(command=cmd, message=msg, send_message_uc=mock_send_uc)


@pytest.mark.asyncio
async def test_ping_handler_replies_pong():
    handler = PingHandler()
    assert handler.command_name == "ping"

    ctx = _make_ctx("!ping")
    await handler.handle(ctx)
    ctx.send_message_uc.execute.assert_awaited_once()
    call_text = ctx.send_message_uc.execute.call_args[0][1]
    assert "pong" in call_text.lower()


@pytest.mark.asyncio
async def test_help_handler_lists_commands():
    class FakeCmd(BaseCommandHandler):
        @property
        def command_name(self):
            return "fake"

        @property
        def description(self):
            return "A fake command"

        async def handle(self, ctx):
            pass

    commands = [PingHandler(), FakeCmd()]
    handler = HelpHandler(lambda: commands)
    assert handler.command_name == "help"

    ctx = _make_ctx("!help")
    await handler.handle(ctx)
    ctx.send_message_uc.execute.assert_awaited_once()
    reply_text = ctx.send_message_uc.execute.call_args[0][1]
    assert "ping" in reply_text
    assert "fake" in reply_text
