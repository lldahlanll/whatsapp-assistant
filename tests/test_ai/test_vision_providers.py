"""Unit tests format multimodal (gambar) per provider: 9router, OpenRouter, Groq, Gemini."""

import base64
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from whatsapp_platform.infrastructure.ai.interfaces import ImagePart, ProviderMessage
from whatsapp_platform.infrastructure.ai.providers.gemini import (
    GeminiProvider,
    _build_gemini_payload,
)
from whatsapp_platform.infrastructure.ai.providers.groq import GroqProvider
from whatsapp_platform.infrastructure.ai.providers.ninerouter import NineRouterProvider
from whatsapp_platform.infrastructure.ai.providers.openai_format import build_openai_content
from whatsapp_platform.infrastructure.ai.providers.openrouter import OpenRouterProvider

IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
IMAGE_B64 = base64.b64encode(IMAGE_BYTES).decode("ascii")
DATA_URI = f"data:image/jpeg;base64,{IMAGE_B64}"


def _image_messages(caption: str = "[Alice]: Ini gambar apa?") -> list[ProviderMessage]:
    return [
        ProviderMessage(role="system", content="Kamu asisten."),
        ProviderMessage(role="assistant", content="Halo!"),
        ProviderMessage(
            role="user",
            content=caption,
            images=[ImagePart(data=IMAGE_BYTES, mime_type="image/jpeg")],
        ),
    ]


def _openai_client() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Itu foto kucing."}}]
    }
    client.post.return_value = resp
    return client


def _assert_openai_multimodal(messages_payload: list[dict]) -> None:
    # System & assistant tetap string biasa
    assert messages_payload[0] == {"role": "system", "content": "Kamu asisten."}
    assert messages_payload[1] == {"role": "assistant", "content": "Halo!"}
    assert messages_payload[2] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "[Alice]: Ini gambar apa?"},
            {"type": "image_url", "image_url": {"url": DATA_URI}},
        ],
    }


# ─── ImagePart & helper OpenAI ────────────────────────────────────────────────


def test_image_part_data_uri_and_base64() -> None:
    part = ImagePart(data=IMAGE_BYTES, mime_type="image/png")
    assert part.base64_data == IMAGE_B64
    assert part.to_data_uri() == f"data:image/png;base64,{IMAGE_B64}"


def test_build_openai_content_text_only_stays_string() -> None:
    msg = ProviderMessage(role="user", content="halo")
    assert build_openai_content(msg) == "halo"


def test_build_openai_content_ignores_images_on_non_user_roles() -> None:
    msg = ProviderMessage(
        role="assistant", content="halo", images=[ImagePart(data=IMAGE_BYTES)]
    )
    assert build_openai_content(msg) == "halo"


def test_build_openai_content_image_without_text_has_only_image_part() -> None:
    msg = ProviderMessage(role="user", content="", images=[ImagePart(data=IMAGE_BYTES)])
    assert build_openai_content(msg) == [
        {"type": "image_url", "image_url": {"url": DATA_URI}}
    ]


# ─── OpenAI-compatible providers ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ninerouter_sends_image_as_image_url_data_uri() -> None:
    client = _openai_client()
    provider = NineRouterProvider(client=client, base_url="http://localhost:4000/v1")

    resp = await provider.generate(_image_messages(), api_key="k", model="vision-pool")

    assert resp.text == "Itu foto kucing."
    payload = client.post.call_args.kwargs["json"]
    assert payload["model"] == "vision-pool"
    _assert_openai_multimodal(payload["messages"])


@pytest.mark.asyncio
async def test_openrouter_sends_image_as_image_url_data_uri() -> None:
    client = _openai_client()
    provider = OpenRouterProvider(client=client)

    await provider.generate(_image_messages(), api_key="k", model="some/vision-model")

    _assert_openai_multimodal(client.post.call_args.kwargs["json"]["messages"])


@pytest.mark.asyncio
async def test_groq_sends_image_as_image_url_data_uri() -> None:
    client = _openai_client()
    provider = GroqProvider(client=client)

    await provider.generate(_image_messages(), api_key="k", model="some-vision-model")

    _assert_openai_multimodal(client.post.call_args.kwargs["json"]["messages"])


@pytest.mark.asyncio
async def test_ninerouter_text_only_payload_unchanged() -> None:
    client = _openai_client()
    provider = NineRouterProvider(client=client, base_url="http://localhost:4000/v1")

    await provider.generate(
        [ProviderMessage(role="user", content="halo")], api_key="k", model="chat-pool"
    )

    assert client.post.call_args.kwargs["json"]["messages"] == [
        {"role": "user", "content": "halo"}
    ]


# ─── Gemini ───────────────────────────────────────────────────────────────────


def test_gemini_payload_uses_inline_data_for_images() -> None:
    payload = _build_gemini_payload(_image_messages())

    assert payload["systemInstruction"] == {"parts": [{"text": "Kamu asisten."}]}
    assert payload["contents"][-1] == {
        "role": "user",
        "parts": [
            {"text": "[Alice]: Ini gambar apa?"},
            {"inline_data": {"mime_type": "image/jpeg", "data": IMAGE_B64}},
        ],
    }


def test_gemini_payload_image_without_caption_omits_empty_text_part() -> None:
    payload = _build_gemini_payload(_image_messages(caption=""))

    assert payload["contents"][-1]["parts"] == [
        {"inline_data": {"mime_type": "image/jpeg", "data": IMAGE_B64}}
    ]


def test_gemini_payload_text_only_user_unchanged() -> None:
    payload = _build_gemini_payload([ProviderMessage(role="user", content="halo")])
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "halo"}]}]


@pytest.mark.asyncio
async def test_gemini_generate_posts_inline_data() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "Itu foto kucing."}]}}]
    }
    client.post.return_value = resp
    provider = GeminiProvider(client=client)

    result = await provider.generate(_image_messages(), api_key="k", model="gemini-flash")

    assert result.text == "Itu foto kucing."
    parts = client.post.call_args.kwargs["json"]["contents"][-1]["parts"]
    assert {"inline_data": {"mime_type": "image/jpeg", "data": IMAGE_B64}} in parts
