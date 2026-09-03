"""Unit tests for NeonizeEventMapper.

Menguji mapping dari Neonize Protobuf events ke Domain events
tanpa memerlukan koneksi WhatsApp nyata.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.events.session_events import (
    QRCodeGenerated,
    SessionConnected,
    SessionDisconnected,
)
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.infrastructure.neonize.event_mapper import NeonizeEventMapper

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_message_ev(
    msg_id: str = "MSG001",
    chat: str = "628111@s.whatsapp.net",
    sender: str = "628222@s.whatsapp.net",
    is_from_me: bool = False,
    push_name: str = "Alice",
    timestamp: int = 1700000000,
    conversation: str = "",
    extended_text: str = "",
    has_image: bool = False,
    has_audio: bool = False,
    has_document: bool = False,
) -> MagicMock:
    """Build a fake Neonize MessageEv protobuf-like mock."""
    ev = MagicMock()

    # Info
    ev.Info.ID = msg_id
    ev.Info.MessageSource.Chat = chat
    ev.Info.MessageSource.Sender = sender
    ev.Info.MessageSource.IsFromMe = is_from_me
    ev.Info.PushName = push_name
    ev.Info.Timestamp = timestamp

    # Message content
    msg = MagicMock()
    msg.conversation = conversation
    msg.extendedTextMessage = MagicMock() if extended_text else None
    if extended_text:
        msg.extendedTextMessage.text = extended_text

    # Image
    msg.imageMessage = MagicMock() if has_image else None
    if has_image:
        msg.imageMessage.caption = "nice pic"
        msg.imageMessage.mimetype = "image/jpeg"

    # Audio
    msg.audioMessage = MagicMock() if has_audio else None
    if has_audio:
        msg.audioMessage.mimetype = "audio/ogg; codecs=opus"
        msg.audioMessage.ptt = True

    # Document
    msg.documentMessage = MagicMock() if has_document else None
    if has_document:
        msg.documentMessage.title = "report.pdf"
        msg.documentMessage.mimetype = "application/pdf"
        msg.documentMessage.fileName = "report.pdf"

    def has_field(name: str) -> bool:
        if name == "conversation":
            return bool(conversation)
        if name == "extendedTextMessage":
            return bool(extended_text)
        if name == "imageMessage":
            return has_image
        if name == "audioMessage":
            return has_audio
        if name == "documentMessage":
            return has_document
        return False

    msg.HasField.side_effect = has_field

    ev.Message = msg
    return ev


# ─── Session Event Mappers ─────────────────────────────────────────────────────


class TestMapSessionEvents:
    def test_map_qr_ev_returns_correct_event(self):
        result = NeonizeEventMapper.map_qr_ev("test-session", "qr-data-abc")
        assert isinstance(result, QRCodeGenerated)
        assert result.session_id == "test-session"
        assert result.qr_code == "qr-data-abc"

    def test_map_qr_ev_empty_qr_string(self):
        result = NeonizeEventMapper.map_qr_ev("sess", "")
        assert isinstance(result, QRCodeGenerated)
        assert result.qr_code == ""

    def test_map_connected_ev_returns_correct_event(self):
        result = NeonizeEventMapper.map_connected_ev("my-session")
        assert isinstance(result, SessionConnected)
        assert result.session_id == "my-session"

    def test_map_disconnected_ev_returns_correct_event(self):
        result = NeonizeEventMapper.map_disconnected_ev("my-session", reason="timeout")
        assert isinstance(result, SessionDisconnected)
        assert result.session_id == "my-session"
        assert result.reason == "timeout"

    def test_map_disconnected_ev_default_reason_empty(self):
        result = NeonizeEventMapper.map_disconnected_ev("sess")
        assert result.reason == ""


# ─── Message Event Mapper ──────────────────────────────────────────────────────


class TestMapMessageEv:
    def test_map_plain_text_message(self):
        ev = _make_message_ev(conversation="Hello World!", msg_id="ID001")
        result = NeonizeEventMapper.map_message_ev(ev)

        assert isinstance(result, MessageReceived)
        msg = result.message
        assert msg is not None
        assert msg.id == "ID001"
        assert isinstance(msg.content, TextContent)
        assert msg.content.text == "Hello World!"

    def test_map_extended_text_message(self):
        ev = _make_message_ev(extended_text="Extended hello")
        result = NeonizeEventMapper.map_message_ev(ev)

        msg = result.message
        assert isinstance(msg.content, TextContent)
        assert msg.content.text == "Extended hello"

    def test_map_image_message(self):
        ev = _make_message_ev(has_image=True)
        result = NeonizeEventMapper.map_message_ev(ev)

        msg = result.message
        assert isinstance(msg.content, MediaContent)
        assert msg.content.media_type == MediaType.IMAGE
        assert msg.content.mime_type == "image/jpeg"
        assert msg.content.caption == "nice pic"

    def test_map_audio_ptt_message(self):
        ev = _make_message_ev(has_audio=True)
        result = NeonizeEventMapper.map_message_ev(ev)

        msg = result.message
        assert isinstance(msg.content, MediaContent)
        assert msg.content.media_type == MediaType.AUDIO
        assert msg.content.is_ptt is True

    def test_map_document_message(self):
        ev = _make_message_ev(has_document=True)
        result = NeonizeEventMapper.map_message_ev(ev)

        msg = result.message
        assert isinstance(msg.content, MediaContent)
        assert msg.content.media_type == MediaType.DOCUMENT
        assert msg.content.file_name == "report.pdf"
        assert msg.content.mime_type == "application/pdf"

    def test_map_message_sender_jid_parsed_correctly(self):
        ev = _make_message_ev(
            sender="628999@s.whatsapp.net",
            chat="628000@s.whatsapp.net",
            conversation="hi",
        )
        result = NeonizeEventMapper.map_message_ev(ev)
        msg = result.message

        assert str(msg.sender_jid) == "628999@s.whatsapp.net"
        assert str(msg.chat_jid) == "628000@s.whatsapp.net"

    def test_map_message_is_from_me_flag(self):
        ev = _make_message_ev(is_from_me=True, conversation="I sent this")
        result = NeonizeEventMapper.map_message_ev(ev)
        assert result.message.is_from_me is True

    def test_map_message_push_name_captured(self):
        ev = _make_message_ev(push_name="Bob", conversation="hey")
        result = NeonizeEventMapper.map_message_ev(ev)
        assert result.message.push_name == "Bob"

    def test_map_message_timestamp_converted_to_utc(self):
        ts = 1700000000
        ev = _make_message_ev(timestamp=ts, conversation="time test")
        result = NeonizeEventMapper.map_message_ev(ev)

        expected = datetime.fromtimestamp(ts, tz=UTC)
        assert result.message.timestamp == expected

    def test_map_message_millisecond_timestamp_handled(self):
        ts_ms = 1700000000000  # Milliseconds
        ev = _make_message_ev(timestamp=ts_ms, conversation="ms time test")
        result = NeonizeEventMapper.map_message_ev(ev)

        expected = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        assert result.message.timestamp == expected

    def test_map_message_fallback_uuid_when_no_id(self):
        ev = _make_message_ev(msg_id="", conversation="no id")
        result = NeonizeEventMapper.map_message_ev(ev)
        # UUID4 should be generated — non-empty string
        assert result.message.id != ""
        assert len(result.message.id) > 0

    def test_map_empty_message_falls_back_to_text_content(self):
        """Ketika tidak ada tipe konten yang cocok, harus fallback ke TextContent kosong."""
        ev = _make_message_ev(conversation="")
        # Pastikan semua media None
        ev.Message.imageMessage = None
        ev.Message.audioMessage = None
        ev.Message.documentMessage = None
        ev.Message.extendedTextMessage = None

        result = NeonizeEventMapper.map_message_ev(ev)
        msg = result.message
        assert isinstance(msg.content, TextContent)
        assert msg.content.text == ""

    def test_map_group_message_jid(self):
        ev = _make_message_ev(
            chat="120363000@g.us",
            sender="628111@s.whatsapp.net",
            conversation="group msg",
        )
        result = NeonizeEventMapper.map_message_ev(ev)
        msg = result.message

        assert msg.chat_jid.is_group is True
        assert msg.sender_jid.is_user is True
