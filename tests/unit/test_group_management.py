"""Unit tests for GroupManagementUseCase and group command handlers."""

from unittest.mock import AsyncMock

import pytest

from tests.mocks.mock_gateway import MockMessagingGateway
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.exceptions.exceptions import GatewayException
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.add import AddHandler
from whatsapp_platform.features.commands.handlers.demote import DemoteHandler
from whatsapp_platform.features.commands.handlers.group_info import GroupInfoHandler
from whatsapp_platform.features.commands.handlers.invite_link import InviteLinkHandler
from whatsapp_platform.features.commands.handlers.kick import KickHandler
from whatsapp_platform.features.commands.handlers.promote import PromoteHandler
from whatsapp_platform.features.commands.handlers.set_name import SetNameHandler


@pytest.fixture
def mock_gateway() -> MockMessagingGateway:
    return MockMessagingGateway()


@pytest.fixture
def group_uc(mock_gateway: MockMessagingGateway) -> GroupManagementUseCase:
    return GroupManagementUseCase(mock_gateway)


class TestGroupManagementUseCase:
    @pytest.mark.asyncio
    async def test_get_group_info(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        info = await group_uc.get_group_info(group_jid)
        assert info["name"] == "Test Group"
        assert info["jid"] == "120363000@g.us"

    @pytest.mark.asyncio
    async def test_get_group_info_raises_for_user_jid(self, group_uc):
        user_jid = JID.parse("6281234567890@s.whatsapp.net")
        with pytest.raises(GatewayException, match="is not a group"):
            await group_uc.get_group_info(user_jid)

    @pytest.mark.asyncio
    async def test_get_invite_link(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        link = await group_uc.get_invite_link(group_jid)
        assert "chat.whatsapp.com/mock-120363000" in link

    @pytest.mark.asyncio
    async def test_kick_member(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        member_jid = JID.parse("628111000000@s.whatsapp.net")
        # should not raise
        await group_uc.kick_member(group_jid, member_jid)

    @pytest.mark.asyncio
    async def test_add_member(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        member_jid = JID.parse("628111000000@s.whatsapp.net")
        await group_uc.add_member(group_jid, member_jid)

    @pytest.mark.asyncio
    async def test_promote_member(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        member_jid = JID.parse("628111000000@s.whatsapp.net")
        await group_uc.promote_member(group_jid, member_jid)

    @pytest.mark.asyncio
    async def test_demote_member(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        member_jid = JID.parse("628111000000@s.whatsapp.net")
        await group_uc.demote_member(group_jid, member_jid)

    @pytest.mark.asyncio
    async def test_change_group_name(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        await group_uc.change_group_name(group_jid, "New Group Name")

    @pytest.mark.asyncio
    async def test_change_group_name_raises_on_empty(self, group_uc):
        group_jid = JID.parse("120363000@g.us")
        with pytest.raises(GatewayException, match="cannot be empty"):
            await group_uc.change_group_name(group_jid, "   ")


def _make_context(
    raw_text: str, is_group: bool = True, group_uc=None
) -> CommandContext:
    send_uc = AsyncMock()
    send_uc.execute = AsyncMock()
    chat_jid = (
        JID.parse("120363000@g.us") if is_group else JID.parse("628111@s.whatsapp.net")
    )
    msg = Message(
        id="M1",
        chat_jid=chat_jid,
        sender_jid=JID.parse("628222@s.whatsapp.net"),
        content=TextContent(text=raw_text),
        direction=MessageDirection.INBOUND,
    )
    cmd = BotCommand.parse(raw_text)
    return CommandContext(
        command=cmd, message=msg, send_message_uc=send_uc, group_mgmt_uc=group_uc
    )


class TestGroupHandlers:
    @pytest.mark.asyncio
    async def test_group_info_handler(self, group_uc):
        ctx = _make_context("!groupinfo", is_group=True, group_uc=group_uc)
        handler = GroupInfoHandler()
        await handler.handle(ctx)
        ctx.send_message_uc.execute.assert_called_once()
        args = ctx.send_message_uc.execute.call_args[0]
        assert "INFORMASI GRUP" in args[1]

    @pytest.mark.asyncio
    async def test_group_info_handler_private_chat_rejected(self, group_uc):
        ctx = _make_context("!groupinfo", is_group=False, group_uc=group_uc)
        handler = GroupInfoHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "hanya dapat digunakan di dalam grup" in args[1]

    @pytest.mark.asyncio
    async def test_invite_link_handler(self, group_uc):
        ctx = _make_context("!invitelink", is_group=True, group_uc=group_uc)
        handler = InviteLinkHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "LINK UNDANGAN GRUP" in args[1]

    @pytest.mark.asyncio
    async def test_kick_handler_via_arg(self, group_uc):
        ctx = _make_context("!kick 628999000111", is_group=True, group_uc=group_uc)
        handler = KickHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil mengeluarkan 628999000111" in args[1]

    @pytest.mark.asyncio
    async def test_kick_handler_via_reply(self, group_uc):
        ctx = _make_context("!kick", is_group=True, group_uc=group_uc)
        ctx.message.quoted_sender_jid = JID.parse("628777000111@s.whatsapp.net")
        handler = KickHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil mengeluarkan 628777000111" in args[1]

    @pytest.mark.asyncio
    async def test_kick_handler_via_mention(self, group_uc):
        ctx = _make_context("!kick", is_group=True, group_uc=group_uc)
        ctx.message.mentioned_jids = [JID.parse("628666000111@s.whatsapp.net")]
        handler = KickHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil mengeluarkan 628666000111" in args[1]

    @pytest.mark.asyncio
    async def test_add_handler(self, group_uc):
        ctx = _make_context("!add 628999000111", is_group=True, group_uc=group_uc)
        handler = AddHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil menambahkan" in args[1]

    @pytest.mark.asyncio
    async def test_promote_handler(self, group_uc):
        ctx = _make_context("!promote 628999000111", is_group=True, group_uc=group_uc)
        handler = PromoteHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil mengangkat" in args[1]

    @pytest.mark.asyncio
    async def test_demote_handler(self, group_uc):
        ctx = _make_context("!demote 628999000111", is_group=True, group_uc=group_uc)
        handler = DemoteHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "Berhasil menurunkan" in args[1]

    @pytest.mark.asyncio
    async def test_set_name_handler(self, group_uc):
        ctx = _make_context("!setname WhatsApp Devs", is_group=True, group_uc=group_uc)
        handler = SetNameHandler()
        await handler.handle(ctx)
        args = ctx.send_message_uc.execute.call_args[0]
        assert "WhatsApp Devs" in args[1]
