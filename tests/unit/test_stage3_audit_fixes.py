"""Regression tests for the stage-3 audit fixes.

1. REST API fails closed when API_KEY is not configured.
2. Group management commands require the sender to be a group admin.
3. LID-addressed senders are mapped to their phone-number JID.
(4. empty AI_ADMIN_JIDS and 5. network fallback are covered in test_ai_audit_fixes.py
 and tests/network/test_permission_and_rate.py.)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from neonize.utils import build_jid  # type: ignore[import-untyped]

from tests.mocks.mock_gateway import MockMessagingGateway
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.kick import KickHandler
from whatsapp_platform.features.commands.handlers.promote import PromoteHandler
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.neonize.event_mapper import NeonizeEventMapper
from whatsapp_platform.presentation.api.app import create_api_app

GROUP = "120363000@g.us"

# ── 1. API fails closed ─────────────────────────────────────────────────────


class _Container:
    def __init__(self, settings: Settings) -> None:
        self._services = {Settings: settings}

    def resolve(self, interface):
        return self._services[interface]


async def test_api_rejects_requests_when_api_key_missing() -> None:
    app = create_api_app(_Container(Settings(api_key="")))  # type: ignore[arg-type]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        protected = await client.get("/api/v1/session")
        health = await client.get("/health")

    assert protected.status_code == 503
    assert health.status_code == 200


async def test_api_rejects_wrong_key() -> None:
    app = create_api_app(_Container(Settings(api_key="right-key")))  # type: ignore[arg-type]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": "wrong"}
    ) as client:
        response = await client.post("/api/v1/session/disconnect")

    assert response.status_code == 401


# ── 2. Group admin required ─────────────────────────────────────────────────


def _group_ctx(text: str, sender: str, group_uc: GroupManagementUseCase) -> CommandContext:
    msg = Message(
        id="M1",
        chat_jid=JID.parse(GROUP),
        sender_jid=JID.parse(sender),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
    )
    return CommandContext(
        command=BotCommand.parse(text), message=msg, send_message_uc=AsyncMock(), group_mgmt_uc=group_uc
    )


def _reply(ctx: CommandContext) -> str:
    return ctx.send_message_uc.execute.call_args[0][1]


async def test_non_admin_member_cannot_promote_or_kick() -> None:
    gateway = MockMessagingGateway()
    gateway.update_group_participants = AsyncMock()  # type: ignore[method-assign]
    group_uc = GroupManagementUseCase(gateway)

    for handler, text in ((PromoteHandler(), "!promote 628333"), (KickHandler(), "!kick 628111")):
        ctx = _group_ctx(text, sender="628333@s.whatsapp.net", group_uc=group_uc)
        await handler.handle(ctx)
        assert "hanya bisa dipakai oleh admin grup" in _reply(ctx)

    gateway.update_group_participants.assert_not_awaited()


async def test_admin_recognised_by_lid() -> None:
    gateway = MockMessagingGateway()
    gateway.update_group_participants = AsyncMock()  # type: ignore[method-assign]
    gateway.get_group_info = AsyncMock(  # type: ignore[method-assign]
        return_value={"participants": [{"jid": "190000000000777@lid", "phone": "", "is_admin": True}]}
    )
    ctx = _group_ctx("!kick 628999", sender="190000000000777@lid", group_uc=GroupManagementUseCase(gateway))

    await KickHandler().handle(ctx)

    gateway.update_group_participants.assert_awaited_once()


async def test_admin_check_fails_closed_when_group_info_unavailable() -> None:
    gateway = MockMessagingGateway()
    gateway.update_group_participants = AsyncMock()  # type: ignore[method-assign]
    gateway.get_group_info = AsyncMock(side_effect=RuntimeError("offline"))  # type: ignore[method-assign]
    ctx = _group_ctx("!kick 628999", sender="628222@s.whatsapp.net", group_uc=GroupManagementUseCase(gateway))

    await KickHandler().handle(ctx)

    assert "Tidak bisa memastikan status admin" in _reply(ctx)
    gateway.update_group_participants.assert_not_awaited()


# ── 3. LID → phone identity ─────────────────────────────────────────────────


def _source(chat: str, sender: str, sender_alt=None, recipient_alt=None) -> SimpleNamespace:
    return SimpleNamespace(Chat=chat, Sender=sender, SenderAlt=sender_alt, RecipientAlt=recipient_alt)


@pytest.mark.parametrize(
    ("chat", "expected_chat"),
    [("111222333@lid", "628123456789@s.whatsapp.net"), (GROUP, GROUP)],
)
def test_lid_sender_mapped_to_phone(chat: str, expected_chat: str) -> None:
    source = _source(chat, "111222333@lid", sender_alt="628123456789@s.whatsapp.net")

    chat_jid, sender_jid = NeonizeEventMapper._prefer_phone_identity(
        source, JID.parse(chat), JID.parse("111222333@lid"), is_from_me=False
    )

    assert str(sender_jid) == "628123456789@s.whatsapp.net"
    assert str(chat_jid) == expected_chat


def test_own_message_in_lid_chat_uses_recipient_alt() -> None:
    recipient_alt = build_jid("628123456789", "s.whatsapp.net")
    source = _source("111222333@lid", "628000@s.whatsapp.net", recipient_alt=recipient_alt)

    chat_jid, _ = NeonizeEventMapper._prefer_phone_identity(
        source, JID.parse("111222333@lid"), JID.parse("628000@s.whatsapp.net"), is_from_me=True
    )

    assert chat_jid.user == "628123456789"


def test_lid_kept_when_no_phone_alt_available() -> None:
    source = _source("111222333@lid", "111222333@lid", sender_alt=None)

    chat_jid, sender_jid = NeonizeEventMapper._prefer_phone_identity(
        source, JID.parse("111222333@lid"), JID.parse("111222333@lid"), is_from_me=False
    )

    assert sender_jid.server == "lid"
    assert chat_jid.server == "lid"
