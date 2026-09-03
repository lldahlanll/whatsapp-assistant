"""Mapper for converting Neonize (v0.4.3.post0) Protobuf events to Domain objects."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from neonize.events import MessageEv  # type: ignore[import-untyped]
from neonize.utils import Jid2String  # type: ignore[import-untyped]

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.events.session_events import (
    QRCodeGenerated,
    SessionConnected,
    SessionDisconnected,
)
from whatsapp_platform.domain.exceptions.exceptions import InvalidJIDError
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.domain.value_objects.message_status import MessageStatus

logger = structlog.get_logger()


class NeonizeEventMapper:
    @staticmethod
    def map_message_ev(ev: MessageEv) -> MessageReceived:
        """Map Neonize MessageEv Protobuf event into MessageReceived domain event."""
        info = getattr(ev, "Info", None)
        message_id = getattr(info, "ID", "") or str(uuid.uuid4())
        push_name = getattr(info, "PushName", "") or None

        source = getattr(info, "MessageSource", None)
        is_from_me = getattr(source, "IsFromMe", False) if source else False

        chat_obj = getattr(source, "Chat", None) if source else None
        sender_obj = getattr(source, "Sender", None) if source else None

        chat_jid_str = (
            Jid2String(chat_obj)
            if chat_obj and hasattr(chat_obj, "User")
            else str(chat_obj or "")
        )
        sender_jid_str = (
            Jid2String(sender_obj)
            if sender_obj and hasattr(sender_obj, "User")
            else str(sender_obj or "")
        )

        chat_jid = JID.parse(chat_jid_str)
        sender_jid = JID.parse(sender_jid_str)

        # Extract text or media content
        msg_obj = getattr(ev, "Message", None)
        text_str = ""
        media_content: MediaContent | None = None

        if msg_obj:
            if NeonizeEventMapper._has_field(msg_obj, "conversation"):
                text_str = msg_obj.conversation
            elif NeonizeEventMapper._has_field(msg_obj, "extendedTextMessage"):
                text_str = getattr(msg_obj.extendedTextMessage, "text", "") or ""
            elif NeonizeEventMapper._has_field(msg_obj, "imageMessage"):
                img = msg_obj.imageMessage
                text_str = getattr(img, "caption", "") or ""
                media_content = MediaContent(
                    media_type=MediaType.IMAGE,
                    mime_type=getattr(img, "mimetype", None),
                    caption=text_str,
                )
            elif NeonizeEventMapper._has_field(msg_obj, "videoMessage"):
                vid = msg_obj.videoMessage
                text_str = getattr(vid, "caption", "") or ""
                media_content = MediaContent(
                    media_type=MediaType.VIDEO,
                    mime_type=getattr(vid, "mimetype", None),
                    caption=text_str,
                )
            elif NeonizeEventMapper._has_field(msg_obj, "audioMessage"):
                aud = msg_obj.audioMessage
                media_content = MediaContent(
                    media_type=MediaType.AUDIO,
                    mime_type=getattr(aud, "mimetype", None),
                    is_ptt=getattr(aud, "ptt", False),
                )
            elif NeonizeEventMapper._has_field(msg_obj, "documentMessage"):
                doc = msg_obj.documentMessage
                text_str = (
                    getattr(doc, "caption", "") or getattr(doc, "title", "") or ""
                )
                file_name = getattr(doc, "fileName", None) or getattr(
                    doc, "title", None
                )
                media_content = MediaContent(
                    media_type=MediaType.DOCUMENT,
                    mime_type=getattr(doc, "mimetype", None),
                    file_name=file_name,
                    caption=text_str,
                )
            elif NeonizeEventMapper._has_field(msg_obj, "stickerMessage"):
                stk = msg_obj.stickerMessage
                media_content = MediaContent(
                    media_type=MediaType.STICKER,
                    mime_type=getattr(stk, "mimetype", None),
                )

        content = media_content or TextContent(text=text_str)
        timestamp = NeonizeEventMapper._parse_timestamp(
            getattr(info, "Timestamp", None)
        )
        quoted_sender_jid, reply_to_id, mentioned_jids = NeonizeEventMapper._extract_context_info(
            msg_obj
        )

        msg_entity = Message(
            id=message_id,
            chat_jid=chat_jid,
            sender_jid=sender_jid,
            content=content,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            timestamp=timestamp,
            push_name=push_name,
            is_from_me=is_from_me,
            reply_to_id=reply_to_id,
            quoted_sender_jid=quoted_sender_jid,
            mentioned_jids=mentioned_jids,
            raw_message=ev,
        )

        return MessageReceived(message=msg_entity, raw_message=ev)

    @staticmethod
    def map_qr_ev(session_id: str, qr_code_str: str) -> QRCodeGenerated:
        return QRCodeGenerated(session_id=session_id, qr_code=qr_code_str)

    @staticmethod
    def map_connected_ev(
        session_id: str, phone_number: str | None = None
    ) -> SessionConnected:
        return SessionConnected(session_id=session_id, phone_number=phone_number)

    @staticmethod
    def map_disconnected_ev(session_id: str, reason: str = "") -> SessionDisconnected:
        return SessionDisconnected(session_id=session_id, reason=reason)

    @staticmethod
    def _parse_timestamp(ts: int | None) -> datetime:
        """Parse unix timestamp safely handling both seconds and milliseconds."""
        if not ts:
            return datetime.now(UTC)
        try:
            ts_sec = ts / 1000.0 if ts > 1e11 else float(ts)
            return datetime.fromtimestamp(ts_sec, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return datetime.now(UTC)

    @staticmethod
    def _has_field(msg_obj: Any, field_name: str) -> bool:
        """Check if a field is present in a Protobuf message or mock object."""
        if not msg_obj:
            return False
        if hasattr(msg_obj, "HasField"):
            try:
                res = msg_obj.HasField(field_name)
                if isinstance(res, bool):
                    return res
            except (ValueError, AttributeError):
                pass
        attr = getattr(msg_obj, field_name, None)
        if attr is None:
            return False
        if isinstance(attr, str):
            return len(attr) > 0
        return True

    @staticmethod
    def _extract_context_info(msg_obj: Any) -> tuple[JID | None, str | None, list[JID]]:
        """Extract quoted sender JID, reply_to_id, and mentioned JIDs from Protobuf contextInfo."""
        if not msg_obj:
            return None, None, []

        ctx = None
        for attr_name in (
            "extendedTextMessage",
            "imageMessage",
            "documentMessage",
            "videoMessage",
            "audioMessage",
            "stickerMessage",
        ):
            sub_msg = getattr(msg_obj, attr_name, None)
            if sub_msg and hasattr(sub_msg, "contextInfo"):
                ctx = getattr(sub_msg, "contextInfo", None)
                if ctx:
                    break

        if not ctx:
            return None, None, []

        quoted_jid = None
        participant = getattr(ctx, "participant", "")
        if participant:
            try:
                quoted_jid = JID.parse(participant)
            except InvalidJIDError:
                logger.warning("Could not parse quoted participant JID", raw=str(participant))

        reply_to_id = None
        stanza_id = getattr(ctx, "stanzaID", "") or getattr(ctx, "stanzaId", "")
        if stanza_id:
            reply_to_id = str(stanza_id)

        mentioned_jids: list[JID] = []
        raw_mentions = getattr(ctx, "mentionedJID", [])
        for m in raw_mentions:
            try:
                mentioned_jids.append(JID.parse(m))
            except InvalidJIDError:
                logger.warning("Could not parse mentioned JID", raw=str(m))

        return quoted_jid, reply_to_id, mentioned_jids

