"""Regression tests for the stage-2 AI audit fixes.

1. AI is off by default for new chats and !ai management is admin-only.
2. Gemini API key travels in a header, never in the (logged) URL.
3. The system prompt carries today's local date.
4. In groups the bot only reacts to mentions of itself.
5. !ai reset really hides earlier history from the LLM (and survives restarts).
"""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.handler import AIMessageHandler
from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.ai_config import AIChatCommandHandler
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse, ProviderMessage
from whatsapp_platform.infrastructure.ai.providers.gemini import GeminiProvider
from whatsapp_platform.infrastructure.ai.sqlite_store import AISQLiteStore
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.logging.setup import setup_logging
from whatsapp_platform.shared.utils.timezone import now_local

ADMIN = "628123456789"
STRANGER = "628555000111"
GROUP = "120363000123456789@g.us"
BOT_LID = "190000000000001"


def _msg(
    text: str,
    sender: str = ADMIN,
    chat: str | None = None,
    msg_id: str = "m1",
    timestamp: datetime | None = None,
    mentioned: list[str] | None = None,
    direction: MessageDirection = MessageDirection.INBOUND,
) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse(chat or f"{sender}@s.whatsapp.net"),
        sender_jid=JID.parse(f"{sender}@s.whatsapp.net"),
        content=TextContent(text=text),
        direction=direction,
        status=MessageStatus.DELIVERED,
        timestamp=timestamp or datetime.now(UTC),
        mentioned_jids=[JID.parse(j) for j in (mentioned or [])],
    )


def _ai_response(text: str = "ok") -> AIResponse:
    return AIResponse(text=text, provider_used="gemini", key_index_used=0, token_usage=None, latency_ms=1.0)


# ── 1. Default off + admin-only management ──────────────────────────────────


def _command_ctx(text: str, sender: str) -> CommandContext:
    send_uc = AsyncMock()
    return CommandContext(
        command=BotCommand.parse(text, prefix="!"),
        message=_msg(text, sender=sender),
        send_message_uc=send_uc,
    )


def _reply_text(ctx: CommandContext) -> str:
    return ctx.send_message_uc.execute.call_args[0][1]


async def test_new_chat_is_disabled_by_default() -> None:
    assert (await AIChatConfigStore().get("x@s.whatsapp.net")).enabled is False
    assert (await AIChatConfigStore(default_enabled=True).get("x@s.whatsapp.net")).enabled is True


@pytest.mark.parametrize("command", ["!ai on", "!ai off", "!ai reset", "!ai model chat-pool", "!ai stats"])
async def test_non_admin_cannot_manage_ai(command: str) -> None:
    store = AIChatConfigStore()
    handler = AIChatCommandHandler(store, AsyncMock(), Settings(ai_admin_jids=ADMIN))
    ctx = _command_ctx(command, sender=STRANGER)

    await handler.handle(ctx)

    assert "khusus admin" in _reply_text(ctx)
    config = await store.get(f"{STRANGER}@s.whatsapp.net")
    assert config.enabled is False
    assert config.model is None


async def test_admin_can_enable_and_status_is_public() -> None:
    store = AIChatConfigStore()
    ai_service = AsyncMock()
    ai_service.get_provider_status.return_value = {}
    handler = AIChatCommandHandler(store, ai_service, Settings(ai_admin_jids=ADMIN))

    admin_ctx = _command_ctx("!ai on", sender=ADMIN)
    await handler.handle(admin_ctx)
    assert "Diaktifkan" in _reply_text(admin_ctx)
    assert (await store.get(f"{ADMIN}@s.whatsapp.net")).enabled is True

    status_ctx = _command_ctx("!ai status", sender=STRANGER)
    await handler.handle(status_ctx)
    assert "STATUS AI" in _reply_text(status_ctx)


async def test_empty_admin_list_allows_nobody() -> None:
    store = AIChatConfigStore()
    handler = AIChatCommandHandler(store, AsyncMock(), Settings(ai_admin_jids=""))

    for sender in (STRANGER, ADMIN):
        ctx = _command_ctx("!ai on", sender=sender)
        await handler.handle(ctx)
        assert "khusus admin" in _reply_text(ctx)
    assert (await store.get(f"{ADMIN}@s.whatsapp.net")).enabled is False


# ── 2. Gemini key never in the URL ──────────────────────────────────────────


async def test_gemini_key_sent_in_header_not_url() -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hai"}]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await GeminiProvider(client).generate(
            [ProviderMessage(role="user", content="halo")], "AIzaSECRET", "gemini-3.5-flash-lite"
        )

    request = captured[0]
    assert "AIzaSECRET" not in str(request.url)
    assert request.headers["x-goog-api-key"] == "AIzaSECRET"


def test_httpx_request_logs_are_suppressed() -> None:
    setup_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


# ── 3 & 5. Date in prompt, reset hides history ──────────────────────────────


def _use_case(history: list[Message]) -> tuple[AIReplyUseCase, AsyncMock]:
    ai_service = AsyncMock()
    ai_service.generate_reply.return_value = _ai_response()
    get_conv = AsyncMock()
    get_conv.execute.return_value = list(reversed(history))  # newest first, like the repository
    return AIReplyUseCase(ai_service=ai_service, get_conv_uc=get_conv, settings=Settings()), ai_service


async def test_system_prompt_contains_local_date() -> None:
    use_case, ai_service = _use_case([])

    await use_case.execute(f"{ADMIN}@s.whatsapp.net", _msg("halo apa kabar", msg_id="t1"))

    system = ai_service.generate_reply.call_args.kwargs["messages"][0].content
    assert now_local().strftime("%Y-%m-%d") in system
    assert "Asia/Jakarta" in system


async def test_history_before_reset_is_not_sent() -> None:
    reset_at = datetime.now(UTC)
    old = _msg("rahasia lama", msg_id="old", timestamp=reset_at - timedelta(minutes=5))
    new = _msg("pesan baru", msg_id="new", timestamp=reset_at + timedelta(seconds=1))
    use_case, ai_service = _use_case([old, new])

    await use_case.execute(f"{ADMIN}@s.whatsapp.net", _msg("lanjut ngobrol", msg_id="t2"), history_since=reset_at)

    contents = [m.content for m in ai_service.generate_reply.call_args.kwargs["messages"]]
    assert not any("rahasia lama" in c for c in contents)
    assert any("pesan baru" in c for c in contents)


async def test_reset_marker_survives_restart() -> None:
    db = AISQLiteStore(":memory:")
    await db.initialize()
    store = AIChatConfigStore(db_store=db)
    reset_at = await store.mark_context_reset("c@s.whatsapp.net")

    reloaded = AIChatConfigStore(db_store=db)
    await reloaded.initialize()

    assert (await reloaded.get("c@s.whatsapp.net")).context_reset_at == reset_at
    await db.close()


async def test_sqlite_store_migrates_old_chat_config_table(tmp_path) -> None:
    db_path = tmp_path / "ai_data.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE chat_config (chat_id TEXT PRIMARY KEY, ai_enabled BOOLEAN NOT NULL DEFAULT 0, "
            "model TEXT NULL, notice_sent BOOLEAN NOT NULL DEFAULT 0, updated_at TIMESTAMP)"
        )
        conn.execute("INSERT INTO chat_config (chat_id, ai_enabled) VALUES ('old@s.whatsapp.net', 1)")

    db = AISQLiteStore(str(db_path))
    await db.initialize()
    configs = await db.load_all_configs()
    await db.close()

    assert configs["old@s.whatsapp.net"].enabled is True
    assert configs["old@s.whatsapp.net"].context_reset_at is None


# ── 4. Group mentions ───────────────────────────────────────────────────────


async def _group_handler(own_ids: set[str]) -> tuple[AIMessageHandler, AsyncMock]:
    ai_reply_uc = AsyncMock()
    ai_reply_uc.execute.return_value = _ai_response()
    gateway = AsyncMock()
    gateway.get_own_user_ids = AsyncMock(return_value=own_ids)
    store = AIChatConfigStore()
    await store.set_enabled(GROUP, True)
    handler = AIMessageHandler(
        ai_reply_uc=ai_reply_uc,
        send_msg_uc=AsyncMock(),
        config_store=store,
        rate_guard=PerChatRateGuard(max_requests=10, window_seconds=60.0),
        settings=Settings(ai_bot_mention_name=""),
        gateway=gateway,
    )
    return handler, ai_reply_uc


async def test_mentioning_another_member_does_not_trigger_bot() -> None:
    handler, ai_reply_uc = await _group_handler({"628999999999", BOT_LID})

    msg = _msg("@budi nanti rapat ya", sender=STRANGER, chat=GROUP, mentioned=["628777777777@s.whatsapp.net"])
    await handler.on_message_received(MessageReceived(message=msg))

    ai_reply_uc.execute.assert_not_awaited()


async def test_mentioning_bot_by_lid_triggers_reply() -> None:
    handler, ai_reply_uc = await _group_handler({"628999999999", BOT_LID})

    msg = _msg("@nara tolong rangkum", sender=STRANGER, chat=GROUP, mentioned=[f"{BOT_LID}@lid"])
    await handler.on_message_received(MessageReceived(message=msg))

    ai_reply_uc.execute.assert_awaited_once()


async def test_unknown_bot_identity_ignores_jid_mentions() -> None:
    handler, ai_reply_uc = await _group_handler(set())

    msg = _msg("@siapa saja", sender=STRANGER, chat=GROUP, mentioned=["628777777777@s.whatsapp.net"])
    await handler.on_message_received(MessageReceived(message=msg))

    ai_reply_uc.execute.assert_not_awaited()
