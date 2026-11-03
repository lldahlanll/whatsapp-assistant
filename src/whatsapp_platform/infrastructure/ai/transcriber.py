"""Transkripsi voice note WhatsApp lewat Groq Whisper (OpenAI-compatible audio API).

Memakai KeyPool Groq yang sama dengan provider chat, sehingga rotasi key dan
cooldown 429 ikut berlaku.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from whatsapp_platform.infrastructure.ai.interfaces import (
    AllProvidersExhaustedError,
    ProviderError,
    RateLimitError,
)
from whatsapp_platform.infrastructure.ai.providers.groq import _parse_groq_retry_after

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.ai.key_pool import KeyPool

logger = structlog.get_logger()

_GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# WhatsApp PTT = "audio/ogg; codecs=opus"; Whisper menebak format dari ekstensi file.
_MIME_EXTENSIONS: dict[str, str] = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/aac": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
}

SUPPORTED_AUDIO_MIME_TYPES: frozenset[str] = frozenset(_MIME_EXTENSIONS)


class GroqWhisperTranscriber:
    """Ubah audio menjadi teks dengan Groq Whisper."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        key_pool: KeyPool,
        model: str = "whisper-large-v3-turbo",
        language: str = "id",
        cooldown_default: float = 60.0,
    ) -> None:
        self._client = client
        self._pool = key_pool
        self._model = model
        self._language = language
        self._cooldown_default = cooldown_default

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        """Kembalikan transkrip (bisa kosong jika audio tidak berisi ucapan).

        Raises:
            AllProvidersExhaustedError: semua key Groq sedang cooldown.
            ProviderError: API menolak permintaan (format rusak, error server, dll).
        """
        ext = _MIME_EXTENSIONS.get(mime_type, "ogg")
        data = {"model": self._model, "response_format": "json", "temperature": "0"}
        if self._language:
            data["language"] = self._language

        last_error: Exception | None = None
        for _attempt in range(self._pool.size()):
            key_info = await self._pool.next_available_key()
            if key_info is None:
                break
            idx, api_key = key_info
            try:
                response = await self._client.post(
                    _GROQ_TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    files={"file": (f"voice.{ext}", audio, mime_type)},
                )
            except httpx.TimeoutException as exc:
                raise ProviderError(f"Groq transcription timed out: {exc}") from exc
            except httpx.RequestError as exc:
                raise ProviderError(f"Groq transcription network error: {exc}") from exc

            if response.status_code == 429:
                retry_after = _parse_groq_retry_after(response, self._cooldown_default)
                await self._pool.mark_rate_limited(idx, retry_after)
                last_error = RateLimitError("Groq transcription rate limited", retry_after=retry_after)
                logger.warning("transcription_rate_limited", key_index=idx, retry_after_seconds=retry_after)
                continue

            if not response.is_success:
                raise ProviderError(
                    f"Groq transcription error {response.status_code}: {response.text[:200]}"
                )

            try:
                text = response.json().get("text", "")
            except ValueError as exc:
                raise ProviderError("Groq transcription returned invalid JSON") from exc
            return str(text or "").strip()

        raise AllProvidersExhaustedError(f"No Groq key available for transcription. Last error: {last_error}")
