"""Unit tests voice note: GroqWhisperTranscriber dan alur transkripsi di AIMessageHandler."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.handler import AIMessageHandler
from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.infrastructure.ai.constants import (
    AI_AUDIO_EMPTY_TRANSCRIPT_MESSAGE,
    AI_AUDIO_TOO_LONG_MESSAGE,
    AI_AUDIO_TRANSCRIPTION_FAILED_MESSAGE,
    AI_AUDIO_UNSUPPORTED_MESSAGE,
)
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    AllProvidersExhaustedError,
    ProviderError,
)
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.transcriber import GroqWhisperTranscriber
from whatsapp_platform.infrastructure.config.settings import Settings

PRIVATE_CHAT = "628123456789@s.whatsapp.net"
GROUP_CHAT = "120363000000000000@g.us"
AUDIO_BYTES = b"OggS-fake-opus"


def _audio_message(
    msg_id: str = "vn1",
    chat_jid: str = PRIVATE_CHAT,
    mime_type: str | None = "audio/ogg; codecs=opus",
    raw_message: object | None = None,
) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse(chat_jid),
        sender_jid=JID.parse("628111111111@s.whatsapp.net"),
        content=MediaContent(media_type=MediaType.AUDIO, mime_type=mime_type, is_ptt=True),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Alice",
        raw_message=raw_message,
    )


def _raw_audio_ev(sha: bytes = b"\x01", seconds: int = 5, file_length: int = len(AUDIO_BYTES)) -> SimpleNamespace:
    return SimpleNamespace(
        Message=SimpleNamespace(
            audioMessage=SimpleNamespace(fileSHA256=sha, seconds=seconds, fileLength=file_length)
        )
    )


async def _make_handler(
    transcript: str | Exception = "catat beli bensin 50rb",
    settings: Settings | None = None,
    chat_jid: str = PRIVATE_CHAT,
    with_transcriber: bool = True,
) -> tuple[AIMessageHandler, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    ai_reply_uc = AsyncMock()
    ai_reply_uc.execute = AsyncMock(
        return_value=AIResponse(
            text="Tercatat.", provider_used="groq", key_index_used=0, token_usage=None, latency_ms=1.0
        )
    )
    send_msg_uc = AsyncMock()
    gateway = AsyncMock()
    gateway.get_own_user_ids = AsyncMock(return_value={"628999999999"})
    gateway.download_media = AsyncMock(return_value=AUDIO_BYTES)
    transcriber = AsyncMock()
    if isinstance(transcript, Exception):
        transcriber.transcribe = AsyncMock(side_effect=transcript)
    else:
        transcriber.transcribe = AsyncMock(return_value=transcript)

    config_store = AIChatConfigStore()
    await config_store.set_enabled(chat_jid, True)
    handler = AIMessageHandler(
        ai_reply_uc=ai_reply_uc,
        send_msg_uc=send_msg_uc,
        config_store=config_store,
        rate_guard=PerChatRateGuard(max_requests=10, window_seconds=60.0),
        settings=settings or Settings(),
        gateway=gateway,
        transcriber=transcriber if with_transcriber else None,
    )
    return handler, ai_reply_uc, send_msg_uc, gateway, transcriber


# ─── AIMessageHandler ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_voice_note_is_transcribed_and_processed_as_text() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway, transcriber = await _make_handler()
    raw = _raw_audio_ev()

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    gateway.download_media.assert_awaited_once_with(raw)
    transcriber.transcribe.assert_awaited_once_with(AUDIO_BYTES, "audio/ogg")
    trigger = ai_reply_uc.execute.call_args.kwargs["trigger_message"]
    assert trigger.content == TextContent(text="catat beli bensin 50rb")
    assert trigger.id == "vn1"  # ID asli dipertahankan untuk idempotency finance
    send_msg_uc.execute.assert_awaited_once_with(PRIVATE_CHAT, "Tercatat.", quoted=None)


@pytest.mark.asyncio
async def test_voice_note_ignored_without_transcriber() -> None:
    handler, ai_reply_uc, _, gateway, _ = await _make_handler(with_transcriber=False)
    raw = _raw_audio_ev()

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_note_ignored_when_disabled_in_settings() -> None:
    handler, ai_reply_uc, _, gateway, _ = await _make_handler(settings=Settings(ai_voice_enabled=False))
    raw = _raw_audio_ev()

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_note_too_long_rejected_before_download() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway, transcriber = await _make_handler(
        settings=Settings(ai_audio_max_seconds=60)
    )
    raw = _raw_audio_ev(seconds=61)

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    gateway.download_media.assert_not_awaited()
    transcriber.transcribe.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(
        PRIVATE_CHAT, AI_AUDIO_TOO_LONG_MESSAGE.format(max_seconds=60), quoted=None
    )


@pytest.mark.asyncio
async def test_voice_note_unsupported_mime_rejected() -> None:
    handler, _, send_msg_uc, gateway, _ = await _make_handler()
    raw = _raw_audio_ev()

    await handler.on_message_received(
        MessageReceived(message=_audio_message(mime_type="audio/amr", raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(PRIVATE_CHAT, AI_AUDIO_UNSUPPORTED_MESSAGE, quoted=None)


@pytest.mark.asyncio
async def test_voice_note_empty_transcript_sends_friendly_message() -> None:
    handler, ai_reply_uc, send_msg_uc, _, _ = await _make_handler(transcript="")
    raw = _raw_audio_ev()

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(PRIVATE_CHAT, AI_AUDIO_EMPTY_TRANSCRIPT_MESSAGE, quoted=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProviderError("boom"), AllProvidersExhaustedError("no keys")])
async def test_voice_note_transcription_failure_sends_friendly_message(error: Exception) -> None:
    handler, ai_reply_uc, send_msg_uc, _, _ = await _make_handler(transcript=error)
    raw = _raw_audio_ev()

    await handler.on_message_received(MessageReceived(message=_audio_message(raw_message=raw), raw_message=raw))

    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(
        PRIVATE_CHAT, AI_AUDIO_TRANSCRIPTION_FAILED_MESSAGE, quoted=None
    )


@pytest.mark.asyncio
async def test_group_voice_note_requires_reply_to_bot() -> None:
    handler, ai_reply_uc, _, gateway, transcriber = await _make_handler(chat_jid=GROUP_CHAT)
    raw = _raw_audio_ev()

    await handler.on_message_received(
        MessageReceived(message=_audio_message(chat_jid=GROUP_CHAT, raw_message=raw), raw_message=raw)
    )

    # Tidak menyebut/membalas bot → tidak diunduh maupun ditranskripsi (hemat kuota)
    gateway.download_media.assert_not_awaited()
    transcriber.transcribe.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_voice_note_events_processed_once() -> None:
    handler, ai_reply_uc, _, _, transcriber = await _make_handler()
    raw = _raw_audio_ev(sha=b"\xaa")

    await handler.on_message_received(MessageReceived(message=_audio_message("a", raw_message=raw), raw_message=raw))
    await handler.on_message_received(MessageReceived(message=_audio_message("b", raw_message=raw), raw_message=raw))

    transcriber.transcribe.assert_awaited_once()
    ai_reply_uc.execute.assert_awaited_once()


# ─── GroqWhisperTranscriber ───────────────────────────────────────────────────


def _transcriber(handler_fn, keys: list[str] | None = None) -> tuple[GroqWhisperTranscriber, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler_fn(request, len(seen))

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return GroqWhisperTranscriber(client, KeyPool(keys or ["k1"]), language="id"), seen


@pytest.mark.asyncio
async def test_transcriber_posts_multipart_and_returns_text() -> None:
    transcriber, seen = _transcriber(lambda req, n: httpx.Response(200, json={"text": "  halo bot  "}))

    assert await transcriber.transcribe(AUDIO_BYTES, "audio/ogg") == "halo bot"

    req = seen[0]
    assert req.url.path == "/openai/v1/audio/transcriptions"
    assert req.headers["Authorization"] == "Bearer k1"
    body = req.read()
    assert b'filename="voice.ogg"' in body
    assert b"whisper-large-v3-turbo" in body
    assert b'name="language"' in body


@pytest.mark.asyncio
async def test_transcriber_rotates_key_on_rate_limit() -> None:
    def respond(req: httpx.Request, n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(429, headers={"retry-after": "30"})
        return httpx.Response(200, json={"text": "ok"})

    transcriber, seen = _transcriber(respond, keys=["k1", "k2"])

    assert await transcriber.transcribe(AUDIO_BYTES, "audio/ogg") == "ok"
    assert [r.headers["Authorization"] for r in seen] == ["Bearer k1", "Bearer k2"]


@pytest.mark.asyncio
async def test_transcriber_raises_when_all_keys_rate_limited() -> None:
    transcriber, _ = _transcriber(lambda req, n: httpx.Response(429))
    with pytest.raises(AllProvidersExhaustedError):
        await transcriber.transcribe(AUDIO_BYTES, "audio/ogg")


@pytest.mark.asyncio
async def test_transcriber_raises_provider_error_on_bad_request() -> None:
    transcriber, _ = _transcriber(lambda req, n: httpx.Response(400, text="invalid file"))
    with pytest.raises(ProviderError):
        await transcriber.transcribe(AUDIO_BYTES, "audio/ogg")
