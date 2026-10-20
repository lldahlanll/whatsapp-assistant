"""Helper format pesan OpenAI-compatible yang dipakai bersama (9router, Groq, OpenRouter)."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.ai.interfaces import ProviderMessage


def build_openai_content(message: ProviderMessage) -> str | list[dict[str, Any]]:
    """Kembalikan field ``content`` untuk satu pesan.

    Pesan tanpa gambar tetap berupa string biasa (payload tidak berubah).
    Pesan user dengan gambar menjadi daftar part multimodal:
    ``[{"type": "text", ...}, {"type": "image_url", "image_url": {"url": "data:..."}}]``.
    """
    if message.role != "user" or not message.images:
        return message.content

    parts: list[dict[str, Any]] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for image in message.images:
        parts.append({"type": "image_url", "image_url": {"url": image.to_data_uri()}})
    return parts
