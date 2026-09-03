"""Penerima event pesan masuk untuk memicu balasan otomatis dari AI."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict
from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.features.customer_lookup.phone_extractor import extract_phone_cores
from whatsapp_platform.infrastructure.ai.constants import (
    AI_FALLBACK_BUSY_MESSAGE,
    AI_FALLBACK_ERROR_MESSAGE,
)
from whatsapp_platform.infrastructure.ai.interfaces import AllProvidersExhaustedError
from whatsapp_platform.infrastructure.config.settings import Settings

if TYPE_CHECKING:
    from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
    from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
    from whatsapp_platform.domain.value_objects.jid import JID

logger = structlog.get_logger()


class AIMessageHandler:
    """Mendengarkan pesan masuk dan membalas secara otomatis menggunakan AI jika fitur aktif."""

    def __init__(
        self,
        ai_reply_uc: AIReplyUseCase,
        send_msg_uc: SendMessageUseCase,
        config_store: AIChatConfigStore,
        rate_guard: PerChatRateGuard,
        settings: Settings,
        message_repo: IMessageRepository | None = None,
        idempotency_ttl_seconds: float = 900.0,
        gateway: IMessagingGateway | None = None,
    ) -> None:
        self._ai_reply_uc = ai_reply_uc
        self._send_msg_uc = send_msg_uc
        self._config_store = config_store
        self._rate_guard = rate_guard
        self._settings = settings
        self._message_repo = message_repo
        self._idempotency_ttl = idempotency_ttl_seconds
        self._gateway = gateway
        self._processed_msg_ids: dict[str, float] = {}
        # Secondary dedup: fingerprint based on content (catches same message with different IDs)
        # TTL is short (10s) — hanya untuk de-bounce duplikat Neonize multi-device
        self._content_fingerprints: dict[str, float] = {}
        self._content_dedup_ttl: float = 10.0
        # Per-chat lock: serializes concurrent MessageEv callbacks for the same chat.
        # Neonize multi-device fires 2 events nearly simultaneously with different IDs;
        # without a lock both coroutines pass the content-fingerprint check before
        # either records the fingerprint → duplicate AI reply.
        self._chat_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _is_duplicate_and_record(self, msg_id: str) -> bool:
        """Check if message_id was recently processed; purge expired entries."""
        now = time.monotonic()
        expired = [mid for mid, ts in self._processed_msg_ids.items() if now - ts > self._idempotency_ttl]
        for mid in expired:
            self._processed_msg_ids.pop(mid, None)

        if msg_id in self._processed_msg_ids:
            return True

        self._processed_msg_ids[msg_id] = now
        return False

    def _is_content_duplicate_and_record(self, chat: str, sender_user: str, text: str) -> bool:
        """Secondary dedup berdasarkan fingerprint konten.

        Neonize/Whatsmeow kadang mengirim 2 MessageEv untuk pesan yang sama
        dengan message_id berbeda (multi-device protocol quirk). Event pertama
        bisa datang dengan sender @s.whatsapp.net, event kedua dengan @lid —
        sehingga str(sender_jid) berbeda meski orangnya sama.

        Solusi: gunakan hanya bagian `user` (angka nomor HP) sebagai kunci
        fingerprint, bukan full JID string.
        """
        now = time.monotonic()
        # Purge expired fingerprints
        expired = [fp for fp, ts in self._content_fingerprints.items() if now - ts > self._content_dedup_ttl]
        for fp in expired:
            self._content_fingerprints.pop(fp, None)

        raw = f"{chat}|{sender_user}|{text}"
        fingerprint = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()
        if fingerprint in self._content_fingerprints:
            return True

        self._content_fingerprints[fingerprint] = now
        return False

    async def on_message_received(self, event: MessageReceived) -> None:
        """Handle inbound WhatsApp message for AI auto-reply."""
        msg = event.message
        if not msg:
            return

        # Serialize processing per chat to prevent race conditions from Neonize
        # multi-device duplicates: two events for the same message arrive nearly
        # simultaneously, so we acquire a per-chat lock before any dedup checks.
        chat_lock = self._chat_locks[str(msg.chat_jid)]
        async with chat_lock:
            await self._handle_message(event, msg)

    async def _handle_message(self, event: MessageReceived, msg: Message) -> None:
        """Core message processing logic, called under per-chat lock."""

        # Guard 0: Idempotency check FIRST
        if msg.id and self._is_duplicate_and_record(msg.id):
            logger.debug(
                "AI reply skipped: duplicate message ID",
                message_id=msg.id,
                chat=str(msg.chat_jid),
            )
            return

        if msg.is_from_me:
            return

        if not isinstance(msg.content, TextContent):
            return

        text = msg.content.text.strip()
        if not text or text.startswith(self._settings.command_prefix):
            return

        # Guard 0b: Content-fingerprint dedup (catches same message with different IDs).
        # Because we are now running under a per-chat lock, this check is atomic:
        # the second duplicate event will always see the fingerprint recorded by
        # the first event before it reaches this point.
        # Use sender_jid.user (numeric only) to normalize LID vs phone-number JID:
        # Neonize fires 2 events — one with @s.whatsapp.net, one with @lid — same
        # person but different full JID strings, which would produce different fingerprints.
        if self._is_content_duplicate_and_record(str(msg.chat_jid), msg.sender_jid.user, text):
            logger.debug(
                "AI reply skipped: duplicate content fingerprint (Neonize multi-device quirk)",
                message_id=msg.id,
                chat=str(msg.chat_jid),
            )
            return

        # Skip AI reply if message is a Customer Lookup query (contains phone numbers)
        if extract_phone_cores(text):
            logger.debug(
                "AI reply skipped: message contains customer lookup phone core",
                message_id=msg.id,
                chat=str(msg.chat_jid),
            )
            return

        chat_jid_str = str(msg.chat_jid)
        config = await self._config_store.get(chat_jid_str)
        if not config.enabled:
            return

        raw_msg = getattr(event, "raw_message", None) or getattr(msg, "raw_message", None)

        # Group chat guard: require bot @mention OR reply to bot message
        if msg.chat_jid.is_group:
            is_mentioned = self._is_bot_mentioned(msg, text)
            is_reply = await self._is_reply_to_bot(msg)
            if not is_mentioned and not is_reply:
                logger.debug(
                    "AI reply skipped: bot neither mentioned nor replied to in group chat",
                    chat=chat_jid_str,
                    message_id=msg.id,
                )
                return
            # Group chat: quote the user's message when replying
            quoted_target = raw_msg or msg.id
        else:
            # Private chat: reply without quoting
            quoted_target = None

        # Per-chat rate guard
        allowed = await self._rate_guard.check_and_record(chat_jid_str)
        if not allowed:
            logger.warning(
                "AI request rate limit exceeded for chat",
                chat=chat_jid_str,
                message_id=msg.id,
            )
            return

        try:
            # 1. Typing ON indicator
            await self._set_typing(msg.chat_jid, composing=True)

            try:
                # 2. Send to LLM & Wait LLM Response
                response = await self._ai_reply_uc.execute(
                    chat_jid_str=chat_jid_str,
                    trigger_message=msg,
                    model_override=config.model,
                )
            finally:
                # 3. Typing OFF indicator (always executed in finally block)
                await self._set_typing(msg.chat_jid, composing=False)

            # 4. Reply to User
            await self._send_msg_uc.execute(chat_jid_str, response.text, quoted=quoted_target)
            logger.info(
                "AI reply sent",
                chat=chat_jid_str,
                message_id=msg.id,
                provider=response.provider_used,
                key_index=response.key_index_used,
                latency_ms=round(response.latency_ms, 1),
            )
        except AllProvidersExhaustedError:
            logger.error("All AI providers exhausted for request", chat=chat_jid_str)
            try:
                await self._send_msg_uc.execute(
                    chat_jid_str,
                    AI_FALLBACK_BUSY_MESSAGE,
                    quoted=quoted_target,
                )
            except Exception as send_exc:  # noqa: BLE001
                logger.error(
                    "Failed to send busy fallback message",
                    chat=chat_jid_str,
                    error=str(send_exc),
                )
        except Exception as exc:
            logger.error(
                "Unhandled error generating AI reply",
                chat=chat_jid_str,
                error=str(exc),
                exc_info=True,
            )
            try:
                await self._send_msg_uc.execute(
                    chat_jid_str,
                    AI_FALLBACK_ERROR_MESSAGE,
                    quoted=quoted_target,
                )
            except Exception as send_exc:  # noqa: BLE001
                logger.error(
                    "Failed to send error fallback message",
                    chat=chat_jid_str,
                    error=str(send_exc),
                )

    async def _set_typing(self, chat_jid: JID, composing: bool) -> None:
        """Send typing presence indicator to chat if gateway is available."""
        if not self._gateway:
            return
        try:
            await self._gateway.send_chat_presence(chat_jid, composing=composing)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send chat presence", chat=str(chat_jid), error=str(exc))

    def _is_bot_mentioned(self, msg: Message, text: str) -> bool:
        """Check if the bot was mentioned via JID metadata or text name."""
        bot_name = self._settings.ai_bot_mention_name.strip().lower()
        if bot_name and f"@{bot_name}" in text.lower():
            return True

        if msg.mentioned_jids:
            return True

        return False

    async def _is_reply_to_bot(self, msg: Message) -> bool:
        """Check if the message is replying to a previous message sent by the bot."""
        if not msg.reply_to_id and not msg.quoted_sender_jid:
            return False

        if msg.reply_to_id and self._message_repo:
            quoted_msg = await self._message_repo.get_by_id(msg.reply_to_id)
            if quoted_msg and (quoted_msg.is_from_me or quoted_msg.direction == MessageDirection.OUTBOUND):
                return True

        if msg.quoted_sender_jid:
            if (
                msg.quoted_sender_jid.user in ("me", "bot")
                or "me@" in str(msg.quoted_sender_jid)
            ):
                return True

        return False
