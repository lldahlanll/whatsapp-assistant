"""Penjaga klaim pengingat palsu: "Pengingat diset" tanpa reminder_create sukses diganti peringatan jujur."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.infrastructure.ai.claim_guard import (
    UNBACKED_REMINDER_REPLY,
    is_unbacked_reminder_claim,
)
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse
from whatsapp_platform.infrastructure.config.settings import Settings

# Kejadian nyata di produksi (bot versi lama tanpa scheduler).
INCIDENT_USER = "Ingatkan 5 menit lagi aku mau makan"
INCIDENT_REPLY = "*Pengingat diset*: 5 menit lagi, kamu mau makan."


@pytest.mark.parametrize(
    "user, reply",
    [
        (INCIDENT_USER, INCIDENT_REPLY),
        ("ingetin minum obat jam 8", "Siap, nanti aku ingatkan jam 8 ya!"),
        ("kabari aku 10 menit lagi", "Oke, aku akan kabari kamu 10 menit lagi."),
        ("besok pagi ingatkan meeting", "Reminder meeting sudah dibuat untuk besok pagi."),
        ("alarm jam 5", "Alarm jam 5 berhasil dipasang."),
    ],
)
def test_fabricated_reminder_claims_are_flagged(user, reply):
    assert is_unbacked_reminder_claim(user, reply)


@pytest.mark.parametrize(
    "user, reply",
    [
        ("halo apa kabar", "Pengingat: jangan lupa istirahat! Kabar baik."),  # tanpa permintaan pengingat
        ("ingetin minum obat jam 8", "Maaf, aku belum bisa menyimpan pengingat itu."),
        ("ingat ya aku suka kopi", "Oke, sudah kucatat kalau kamu suka kopi."),
        ("cara bikin alarm di hp gimana?", "Buka aplikasi Jam, lalu ketuk tombol tambah."),
    ],
)
def test_honest_or_unrelated_replies_pass(user, reply):
    assert not is_unbacked_reminder_claim(user, reply)


def _msg(text: str) -> Message:
    jid = JID.parse("628123456789@s.whatsapp.net")
    return Message(
        id="m1",
        chat_jid=jid,
        sender_jid=jid,
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Alice",
    )


def _resp(text: str) -> AIResponse:
    return AIResponse(text=text, provider_used="x", key_index_used=0, token_usage=None, latency_ms=1.0)


def _use_case(ai_service, tool_executor, settings=None) -> AIReplyUseCase:
    conv = AsyncMock()
    conv.execute = AsyncMock(return_value=[])
    ai_service.append_to_context = AsyncMock()
    return AIReplyUseCase(
        ai_service=ai_service, get_conv_uc=conv, tool_executor=tool_executor, settings=settings or Settings()
    )


def _executor(status: str) -> AsyncMock:
    ex = AsyncMock()
    ex.is_enabled = True
    ex.execute = AsyncMock(return_value=json.dumps({"status": status}))
    return ex


async def test_tool_path_blocks_claim_when_tool_not_called():
    ai = AsyncMock()
    ai.generate_reply_with_tools = AsyncMock(return_value=_resp(INCIDENT_REPLY))
    out = await _use_case(ai, _executor("success")).execute("c", _msg(INCIDENT_USER))
    assert out.text == UNBACKED_REMINDER_REPLY


async def test_tool_path_blocks_claim_when_tool_failed():
    ai = AsyncMock()
    ex = _executor("error")

    async def fake(**kwargs):
        await kwargs["tool_executor"].execute(
            tool_name="reminder_create", arguments={}, user_jid=None, chat_jid=None
        )
        return _resp(INCIDENT_REPLY)

    ai.generate_reply_with_tools = AsyncMock(side_effect=fake)
    out = await _use_case(ai, ex).execute("c", _msg(INCIDENT_USER))
    assert out.text == UNBACKED_REMINDER_REPLY


async def test_tool_path_keeps_claim_when_reminder_saved():
    ai = AsyncMock()
    ex = _executor("success")

    async def fake(**kwargs):
        await kwargs["tool_executor"].execute(
            tool_name="reminder_create", arguments={}, user_jid=None, chat_jid=None
        )
        return _resp("Pengingat no. 1 tersimpan, dikirim 5 menit lagi.")

    ai.generate_reply_with_tools = AsyncMock(side_effect=fake)
    out = await _use_case(ai, ex).execute("c", _msg(INCIDENT_USER))
    assert out.text.startswith("Pengingat no. 1 tersimpan")
    ex.execute.assert_awaited_once()


async def test_plain_path_blocks_claim_when_scheduler_disabled():
    ai = AsyncMock()
    ai.generate_reply = AsyncMock(return_value=_resp(INCIDENT_REPLY))
    out = await _use_case(ai, _executor("success"), Settings(scheduler_enabled=False)).execute(
        "c", _msg(INCIDENT_USER)
    )
    ai.generate_reply.assert_awaited_once()
    assert out.text == UNBACKED_REMINDER_REPLY
