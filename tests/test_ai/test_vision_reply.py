"""Unit tests alur vision: AIMessageHandler (unduh + batas ukuran) dan AIReplyUseCase (intent image)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
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
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.constants import (
    AI_IMAGE_DEFAULT_PROMPT,
    AI_IMAGE_DOWNLOAD_FAILED_MESSAGE,
    AI_IMAGE_TOO_LARGE_MESSAGE,
    AI_IMAGE_UNSUPPORTED_MESSAGE,
)
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse, ProviderMessage
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy
from whatsapp_platform.infrastructure.config.settings import Settings

PRIVATE_CHAT = "628123456789@s.whatsapp.net"
GROUP_CHAT = "120363000000000000@g.us"
IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"


def _image_message(
    msg_id: str = "img1",
    caption: str | None = "Ini apa?",
    chat_jid: str = PRIVATE_CHAT,
    mime_type: str | None = "image/jpeg",
    file_bytes: bytes | None = None,
    mentioned: bool = False,
    raw_message: object | None = None,
) -> Message:
    return Message(
        id=msg_id,
        chat_jid=JID.parse(chat_jid),
        sender_jid=JID.parse("628111111111@s.whatsapp.net"),
        content=MediaContent(
            media_type=MediaType.IMAGE,
            mime_type=mime_type,
            caption=caption,
            file_bytes=file_bytes,
        ),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Alice",
        mentioned_jids=[JID.parse("628999999999@s.whatsapp.net")] if mentioned else [],
        raw_message=raw_message,
    )


def _raw_image_ev(sha: bytes = b"\x01\x02", file_length: int = len(IMAGE_BYTES)) -> SimpleNamespace:
    """Tiruan MessageEv Neonize: ev.Message.imageMessage.{fileSHA256,fileLength}."""
    return SimpleNamespace(
        Message=SimpleNamespace(
            imageMessage=SimpleNamespace(fileSHA256=sha, fileLength=file_length)
        )
    )


def _ai_response() -> AIResponse:
    return AIResponse(
        text="Itu foto kucing.",
        provider_used="ninerouter",
        key_index_used=0,
        token_usage=None,
        latency_ms=5.0,
    )


async def _make_handler(
    settings: Settings | None = None,
    download_result: bytes | Exception = IMAGE_BYTES,
    with_gateway: bool = True,
    chat_jid: str = PRIVATE_CHAT,
) -> tuple[AIMessageHandler, AsyncMock, AsyncMock, AsyncMock]:
    ai_reply_uc = AsyncMock()
    ai_reply_uc.execute = AsyncMock(return_value=_ai_response())
    send_msg_uc = AsyncMock()
    gateway = AsyncMock()
    if isinstance(download_result, Exception):
        gateway.download_media = AsyncMock(side_effect=download_result)
    else:
        gateway.download_media = AsyncMock(return_value=download_result)

    config_store = AIChatConfigStore()
    await config_store.set_enabled(chat_jid, True)

    handler = AIMessageHandler(
        ai_reply_uc=ai_reply_uc,
        send_msg_uc=send_msg_uc,
        config_store=config_store,
        rate_guard=PerChatRateGuard(max_requests=10, window_seconds=60.0),
        settings=settings or Settings(),
        gateway=gateway if with_gateway else None,
    )
    return handler, ai_reply_uc, send_msg_uc, gateway


# ─── AIMessageHandler ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_downloads_image_and_passes_bytes_to_use_case() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler()
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_awaited_once_with(raw)
    trigger = ai_reply_uc.execute.call_args.kwargs["trigger_message"]
    assert isinstance(trigger.content, MediaContent)
    assert trigger.content.file_bytes == IMAGE_BYTES
    assert trigger.content.mime_type == "image/jpeg"
    assert trigger.content.caption == "Ini apa?"
    send_msg_uc.execute.assert_awaited_once_with(PRIVATE_CHAT, "Itu foto kucing.", quoted=None)


@pytest.mark.asyncio
async def test_handler_accepts_image_without_caption() -> None:
    handler, ai_reply_uc, _, gateway = await _make_handler()
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(caption=None, raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_awaited_once()
    ai_reply_uc.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_group_image_requires_mention() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler(chat_jid=GROUP_CHAT)
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(chat_jid=GROUP_CHAT, raw_message=raw), raw_message=raw)
    )
    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()

    raw2 = _raw_image_ev(sha=b"\x09")
    mentioned = _image_message(
        msg_id="img2", chat_jid=GROUP_CHAT, mentioned=True, raw_message=raw2
    )
    await handler.on_message_received(MessageReceived(message=mentioned, raw_message=raw2))
    gateway.download_media.assert_awaited_once_with(raw2)
    ai_reply_uc.execute.assert_awaited_once()
    # Group reply mengutip pesan asli
    assert send_msg_uc.execute.call_args.kwargs["quoted"] is raw2


@pytest.mark.asyncio
async def test_handler_rejects_image_over_size_limit_after_download() -> None:
    settings = Settings(ai_image_max_bytes=4)
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler(settings=settings)
    # fileLength tidak diketahui → tetap diunduh, lalu ditolak karena ukuran aktual
    raw = _raw_image_ev(file_length=0)

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_awaited_once()
    ai_reply_uc.execute.assert_not_awaited()
    expected = AI_IMAGE_TOO_LARGE_MESSAGE.format(max_mb=f"{4 / (1024 * 1024):g}")
    send_msg_uc.execute.assert_awaited_once_with(PRIVATE_CHAT, expected, quoted=None)


@pytest.mark.asyncio
async def test_handler_rejects_declared_oversize_without_downloading() -> None:
    settings = Settings(ai_image_max_bytes=1024 * 1024)
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler(settings=settings)
    raw = _raw_image_ev(file_length=10 * 1024 * 1024)

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(
        PRIVATE_CHAT, AI_IMAGE_TOO_LARGE_MESSAGE.format(max_mb="1"), quoted=None
    )


@pytest.mark.asyncio
async def test_handler_rejects_unsupported_mime_type() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler()
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(mime_type="image/gif", raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(
        PRIVATE_CHAT, AI_IMAGE_UNSUPPORTED_MESSAGE, quoted=None
    )


@pytest.mark.asyncio
async def test_handler_download_failure_sends_friendly_message() -> None:
    handler, ai_reply_uc, send_msg_uc, _ = await _make_handler(
        download_result=RuntimeError("media expired")
    )
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_awaited_once_with(
        PRIVATE_CHAT, AI_IMAGE_DOWNLOAD_FAILED_MESSAGE, quoted=None
    )


@pytest.mark.asyncio
async def test_handler_ignores_image_when_vision_disabled() -> None:
    handler, ai_reply_uc, send_msg_uc, gateway = await _make_handler(
        settings=Settings(ai_vision_enabled=False)
    )
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_skips_image_without_gateway() -> None:
    handler, ai_reply_uc, send_msg_uc, _ = await _make_handler(with_gateway=False)
    raw = _raw_image_ev()

    await handler.on_message_received(
        MessageReceived(message=_image_message(raw_message=raw), raw_message=raw)
    )

    ai_reply_uc.execute.assert_not_awaited()
    send_msg_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_skips_image_caption_command() -> None:
    handler, ai_reply_uc, _, gateway = await _make_handler()
    raw = _raw_image_ev()
    settings = Settings()

    await handler.on_message_received(
        MessageReceived(
            message=_image_message(caption=f"{settings.command_prefix}ping", raw_message=raw),
            raw_message=raw,
        )
    )

    gateway.download_media.assert_not_awaited()
    ai_reply_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_dedups_same_image_but_not_different_images() -> None:
    handler, ai_reply_uc, _, _ = await _make_handler()
    raw_a = _raw_image_ev(sha=b"\xaa")
    raw_b = _raw_image_ev(sha=b"\xbb")

    # Duplikat multi-device: ID berbeda, file sama → hanya sekali
    await handler.on_message_received(
        MessageReceived(message=_image_message(msg_id="a1", caption=None, raw_message=raw_a), raw_message=raw_a)
    )
    await handler.on_message_received(
        MessageReceived(message=_image_message(msg_id="a2", caption=None, raw_message=raw_a), raw_message=raw_a)
    )
    assert ai_reply_uc.execute.await_count == 1

    # Gambar lain tanpa caption → tetap diproses
    await handler.on_message_received(
        MessageReceived(message=_image_message(msg_id="b1", caption=None, raw_message=raw_b), raw_message=raw_b)
    )
    assert ai_reply_uc.execute.await_count == 2


# ─── AIReplyUseCase ───────────────────────────────────────────────────────────


class _RecordingProvider:
    """Provider palsu yang merekam model & pesan yang diterima."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[tuple[str, list[ProviderMessage]]] = []

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def supports_tool_calling(self) -> bool:
        return True

    async def generate(self, messages, api_key, model):
        self.calls.append((model, messages))
        return _ai_response()

    async def generate_with_tools(self, messages, tools, api_key, model):  # pragma: no cover
        raise AssertionError("Image intent must not use tools")


def _make_use_case(
    provider: _RecordingProvider, tool_executor: object | None = None
) -> tuple[AIReplyUseCase, AIService]:
    ai_service = AIService(
        providers={provider.provider_name: (provider, KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy([provider.provider_name]),
        default_models={"ninerouter": "chat-pool"},
        intent_models={"ninerouter": {"chat": "chat-pool", "image": "vision-pool"}},
    )
    get_conv_uc = AsyncMock()
    get_conv_uc.execute = AsyncMock(return_value=[])
    use_case = AIReplyUseCase(
        ai_service=ai_service,
        get_conv_uc=get_conv_uc,
        tool_executor=tool_executor,  # type: ignore[arg-type]
    )
    return use_case, ai_service


@pytest.mark.asyncio
async def test_use_case_routes_image_to_vision_model_with_image_part() -> None:
    provider = _RecordingProvider("ninerouter")
    use_case, _ = _make_use_case(provider)

    msg = _image_message(caption="Ini apa?", file_bytes=IMAGE_BYTES)
    res = await use_case.execute(PRIVATE_CHAT, msg)

    assert res.text == "Itu foto kucing."
    model, messages = provider.calls[0]
    assert model == "vision-pool"
    last = messages[-1]
    assert last.role == "user"
    assert last.content == "[Alice]: Ini apa?"
    assert last.images is not None and len(last.images) == 1
    assert last.images[0].data == IMAGE_BYTES
    assert last.images[0].mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_use_case_image_without_caption_uses_default_prompt() -> None:
    provider = _RecordingProvider("ninerouter")
    use_case, _ = _make_use_case(provider)

    await use_case.execute(PRIVATE_CHAT, _image_message(caption=None, file_bytes=IMAGE_BYTES))

    _, messages = provider.calls[0]
    assert messages[-1].content == f"[Alice]: {AI_IMAGE_DEFAULT_PROMPT}"


@pytest.mark.asyncio
async def test_use_case_image_calls_generate_reply_with_image_intent_even_with_tools() -> None:
    provider = _RecordingProvider("ninerouter")
    tool_executor = SimpleNamespace(is_enabled=True)
    use_case, ai_service = _make_use_case(provider, tool_executor=tool_executor)
    ai_service.generate_reply = AsyncMock(return_value=_ai_response())  # type: ignore[method-assign]
    ai_service.generate_reply_with_tools = AsyncMock()  # type: ignore[method-assign]

    # Caption berbau finance tetap ke intent image (tanpa tools)
    await use_case.execute(
        PRIVATE_CHAT, _image_message(caption="catat struk belanja ini", file_bytes=IMAGE_BYTES)
    )

    ai_service.generate_reply_with_tools.assert_not_awaited()
    kwargs = ai_service.generate_reply.call_args.kwargs
    assert kwargs["intent"] == "image"
    assert kwargs["messages"][-1].images


@pytest.mark.asyncio
async def test_use_case_persists_text_marker_not_image_bytes() -> None:
    provider = _RecordingProvider("ninerouter")
    use_case, ai_service = _make_use_case(provider)

    await use_case.execute(PRIVATE_CHAT, _image_message(caption="Ini apa?", file_bytes=IMAGE_BYTES))

    context = await ai_service.get_context(PRIVATE_CHAT)
    assert context[0].role == "user"
    assert context[0].content == "[Alice]: [gambar] Ini apa?"
    assert context[0].images is None


@pytest.mark.asyncio
async def test_use_case_text_message_still_uses_chat_model() -> None:
    provider = _RecordingProvider("ninerouter")
    use_case, _ = _make_use_case(provider)

    text_msg = Message(
        id="t1",
        chat_jid=JID.parse(PRIVATE_CHAT),
        sender_jid=JID.parse(PRIVATE_CHAT),
        content=TextContent(text="halo"),
        direction=MessageDirection.INBOUND,
        push_name="Alice",
    )
    await use_case.execute(PRIVATE_CHAT, text_msg)

    model, messages = provider.calls[0]
    assert model == "chat-pool"
    assert messages[-1].images is None
