"""Unit tests for CommandRouter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.router import CommandRouter


def _make_text_message(text: str, is_from_me: bool = False) -> Message:
    return Message(
        id="test-001",
        chat_jid=JID.parse("628111111111@s.whatsapp.net"),
        sender_jid=JID.parse("628222222222@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        is_from_me=is_from_me,
    )


class EchoHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo test command"

    async def handle(self, ctx: CommandContext) -> None:
        await ctx.reply(" ".join(ctx.command.args))


@pytest.mark.asyncio
async def test_command_router_dispatches_registered_command():
    mock_event_bus = AsyncMock()
    mock_send_uc = AsyncMock()
    mock_send_uc.execute = AsyncMock(return_value=MagicMock())

    router = CommandRouter(mock_send_uc, mock_event_bus, prefix="!")
    router.register(EchoHandler())

    msg = _make_text_message("!echo hello world")
    event = MessageReceived(message=msg)

    await router.on_message_received(event)
    mock_send_uc.execute.assert_awaited_once()
    call_args = mock_send_uc.execute.call_args
    assert "hello world" in call_args[0]


@pytest.mark.asyncio
async def test_command_router_middleware_can_block_execution():
    mock_event_bus = AsyncMock()
    mock_send_uc = AsyncMock()

    router = CommandRouter(mock_send_uc, mock_event_bus, prefix="!")
    router.register(EchoHandler())

    async def blocking_middleware(ctx: CommandContext) -> bool:
        return False  # Abort command pipeline

    router.use_middleware(blocking_middleware)

    msg = _make_text_message("!echo hello")
    event = MessageReceived(message=msg)

    await router.on_message_received(event)
    mock_send_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_router_ignores_from_me_messages():
    mock_event_bus = AsyncMock()
    mock_send_uc = AsyncMock()

    router = CommandRouter(mock_send_uc, mock_event_bus)
    router.register(EchoHandler())

    msg = _make_text_message("!echo hello", is_from_me=True)
    event = MessageReceived(message=msg)

    await router.on_message_received(event)
    mock_send_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_router_publishes_unknown_command():
    mock_event_bus = AsyncMock()
    mock_event_bus.publish = AsyncMock()
    mock_send_uc = AsyncMock()

    router = CommandRouter(mock_send_uc, mock_event_bus, prefix="!")

    msg = _make_text_message("!unknown_cmd")
    event = MessageReceived(message=msg)

    await router.on_message_received(event)
    mock_event_bus.publish.assert_awaited_once()
