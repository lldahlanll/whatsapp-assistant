"""MessageContent Value Objects for Text, Image, Audio, Document media."""

from dataclasses import dataclass
from enum import Enum


class MediaType(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    VIDEO = "VIDEO"
    STICKER = "STICKER"


@dataclass(frozen=True)
class TextContent:
    text: str

    @property
    def media_type(self) -> MediaType:
        return MediaType.TEXT


@dataclass(frozen=True)
class MediaContent:
    media_type: MediaType
    file_bytes: bytes | None = None
    file_path: str | None = None
    url: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    file_name: str | None = None
    is_ptt: bool = False  # Push-to-talk voice note for audio


MessageContent = TextContent | MediaContent
