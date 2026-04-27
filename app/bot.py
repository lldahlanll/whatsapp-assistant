import asyncio
import re
import time
import traceback
from typing import Optional

from loguru import logger
from neonize.aioze.client import NewAClient
from neonize.aioze.events import ConnectedEv, DisconnectedEv, MessageEv
from neonize.proto.Neonize_pb2 import JID
from neonize.utils.enum import ChatPresence, ChatPresenceMedia

from app.ai import route_and_generate
from app.ai.prompts import ChatContext
from app.config import settings
from app.memory import memory_manager
from app.utils.locks import jid_lock_manager
from app.utils.stats import stats_tracker

COMMANDS = {
    "/reset": "Hapus riwayat percakapan",
    "/stats": "Lihat statistik percakapan",
    "/help":  "Tampilkan daftar perintah",
    "/ping":  "Cek bot aktif",
}


class WhatsAppBot:
    def __init__(self) -> None:
        self.client = NewAClient(settings.session_db_path)
        self.bot_jid: str = ""
        self.bot_lid: str = ""
        self.bot_number: str = ""
        self._stop_event = asyncio.Event()
        self._register_events()

    # ── Event registration ────────────────────────────────────

    def _register_events(self) -> None:
        @self.client.event(ConnectedEv)
        async def on_connected(client: NewAClient, event: ConnectedEv):
            try:
                me = await client.get_me()
                self.bot_jid = f"{me.JID.User}@{me.JID.Server}"
                self.bot_number = me.JID.User
                # Konsisten pakai .User (uppercase) — sesuai proto neonize
                if hasattr(me, "LID") and me.LID and me.LID.User:
                    self.bot_lid = f"{me.LID.User}@{me.LID.Server}"
            except Exception as e:
                logger.warning(f"[Bot] Could not get bot JID: {e}")  # f-string fix

            redis_ok = await memory_manager.ping()
            logger.info(f"[Bot] ✓ Connected as: {self.bot_jid}")
            logger.info(f"[Bot] LID: {self.bot_lid or '(none)'}")
            logger.info(f"[Bot] Bot number: {self.bot_number}")
            logger.info(f"[Bot] Bot name: {settings.bot_name}")
            logger.info(f"[Bot] Redis: {'✓ OK' if redis_ok else '✗ FAIL'}")

        @self.client.event(DisconnectedEv)
        async def on_disconnected(client: NewAClient, event: DisconnectedEv):
            logger.warning("[Bot] ✗ Disconnected from WhatsApp")

        @self.client.event(MessageEv)
        async def on_message(client: NewAClient, event: MessageEv):
            # Spawn task agar event loop tidak ke-block
            asyncio.create_task(self._handle_message_safe(client, event))

    # ── Message handler dengan per-JID lock ───────────────────

    async def _handle_message_safe(
        self, client: NewAClient, event: MessageEv
    ) -> None:
        """Wrapper yang catch semua exception."""
        try:
            await self._handle_message(client, event)
        except Exception as e:
            logger.error(f"[Bot] Unhandled error: {e}")
            logger.error(f"[Bot] Traceback:\n{traceback.format_exc()}")

    async def _handle_message(
        self, client: NewAClient, event: MessageEv
    ) -> None:
        source = event.Info.MessageSource
        if source.IsFromMe:
            return

        text = self._extract_text(event)
        if not text:
            return

        sender_jid = f"{source.Sender.User}@{source.Sender.Server}"
        chat_jid = f"{source.Chat.User}@{source.Chat.Server}"
        is_group = source.IsGroup
        push_name = event.Info.Pushname or "unknown"

        logger.info(
            f"[Bot] {'GROUP' if is_group else 'PRIVATE'} | "
            f"From: {sender_jid} ({push_name}) | "
            f"Text: {text[:60]}{'...' if len(text) > 60 else ''}"
        )

        # ── Rate limit per sender (bukan per chat) ────────────
        if await memory_manager.is_rate_limited(sender_jid):
            logger.warning(f"[Bot] ⚠️ SPAM dari {sender_jid}, ignored")
            return

        await stats_tracker.track_message_received(chat_jid, is_group)

        # Filter group: hanya balas kalau di-mention atau di-reply
        if is_group and not self._should_reply_in_group(event, text):
            return

        # ── Per-JID lock: serialize per chat ──────────────────
        try:
            async with jid_lock_manager.acquire(chat_jid, timeout=120.0):
                await self._process_message(
                    client, event, chat_jid, push_name, is_group, text
                )
        except asyncio.TimeoutError:
            logger.error(
                f"[Bot] Lock timeout for {chat_jid} — pesan dari {sender_jid} di-skip"
            )
            # Optional: kasih tau user
            try:
                await self._send_reply(
                    client, event,
                    "⚠️ Bot sedang sibuk, coba lagi sebentar."
                )
            except Exception:
                pass

    async def _process_message(
        self,
        client: NewAClient,
        event: MessageEv,
        chat_jid: str,
        push_name: str,
        is_group: bool,
        text: str,
    ) -> None:
        await memory_manager.save_meta(
            jid=chat_jid,
            push_name=push_name,
            is_group=is_group,
        )

        # ── Command ───────────────────────────────────────────
        if text.startswith("/"):
            response = await self._handle_command(text, chat_jid)
            if response:
                await self._send_reply(client, event, self._format_md(response))
            return

         # ── AI generation dengan layered prompt ──────────────
        await memory_manager.add_message(chat_jid, "user", text)
        history = await memory_manager.get_history(chat_jid)

        # Build chat context
        chat_context = ChatContext(
            push_name=push_name,
            is_group=is_group,
            timezone_offset=7,  # WIB
        )

        await self._send_typing(client, event.Info.MessageSource.Chat, True)

        t_start = time.monotonic()
        try:
            response, model_used = await route_and_generate(
                history=history,
                user_text=text,
                context=chat_context,
            )
        finally:
            await self._send_typing(client, event.Info.MessageSource.Chat, False)
        t_elapsed_ms = (time.monotonic() - t_start) * 1000

        if response:
            await stats_tracker.track_response(model_used, True, t_elapsed_ms)
            await memory_manager.add_message(chat_jid, "assistant", response)
            logger.info(
                f"[Bot] ✓ {model_used} | {len(response)} chars | "
                f"{t_elapsed_ms:.0f}ms"
            )
            await self._send_reply(client, event, self._format_md(response))
        else:
            await stats_tracker.track_response("none", False, t_elapsed_ms)
            logger.error("[Bot] All models failed")
            await self._send_reply(
                client, event,
                "⚠️ Maaf, lagi ada gangguan teknis. Coba lagi sebentar lagi ya."
            )

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _extract_text(event: MessageEv) -> str:
        msg = event.Message
        if msg.conversation:
            return msg.conversation.strip()
        if msg.extendedTextMessage and msg.extendedTextMessage.text:
            return msg.extendedTextMessage.text.strip()
        if msg.listResponseMessage and msg.listResponseMessage.title:
            return msg.listResponseMessage.title.strip()
        if (msg.buttonsResponseMessage
                and msg.buttonsResponseMessage.selectedDisplayText):
            return msg.buttonsResponseMessage.selectedDisplayText.strip()
        return ""
    
    def _is_self_jid(self, jid_str: str) -> bool:
        """Cek apakah JID merujuk ke bot — agnostik @s.whatsapp.net / @lid / @c.us."""
        if not jid_str:
            return False
        if jid_str == self.bot_jid or jid_str == self.bot_lid:
            return True
        # Compare hanya bagian User (nomor), buang device suffix kalau ada
        user_part = jid_str.split("@")[0].split(":")[0]
        if user_part == self.bot_number:
            return True
        if self.bot_lid:
            lid_user = self.bot_lid.split("@")[0].split(":")[0]
            if user_part == lid_user:
                return True
        return False

    def _should_reply_in_group(self, event: MessageEv, text: str) -> bool:
        if not self.bot_number:
            return False

        msg = event.Message
        ctx = msg.extendedTextMessage.contextInfo if msg.extendedTextMessage else None

        if ctx:
            for j in (ctx.mentionedJID or []):
                jid_str = j if isinstance(j, str) else f"{j.User}@{j.Server}"
                if self._is_self_jid(jid_str):
                    return True

            if ctx.participant:
                participant_jid = f"{ctx.participant.User}@{ctx.participant.Server}"
                if self._is_self_jid(participant_jid):
                    return True

        if f"@{self.bot_number}" in text:
            return True
        if self.bot_lid and f"@{self.bot_lid.split('@')[0]}" in text:
            return True

        return False
    
    @staticmethod
    def _format_md(text: str) -> str:
        """Convert Markdown → WhatsApp format."""
        text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)
        text = re.sub(r"#{1,6}\s*(.*)", r"*\1*", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        return text

    async def _handle_command(self, text: str, jid: str) -> str:
        cmd = text.strip().lower().split()[0]
        await stats_tracker.track_command(cmd)

        if cmd == "/reset":
            ok = await memory_manager.clear_history(jid)
            return (
                "🗑️ Riwayat percakapan berhasil dihapus. Mulai dari awal!"
                if ok else
                "⚠️ Gagal menghapus riwayat. Coba lagi."
            )

        if cmd == "/stats":
            stats = await memory_manager.get_stats(jid)
            if stats:
                return (
                    f"📊 *Statistik Percakapan*\n"
                    f"├ Pesan tersimpan : {stats['message_count']}/{stats['max_history']}\n"
                    f"├ TTL             : {stats['ttl_hours']} jam tersisa\n"
                    f"└ Chat ID         : ...{jid[-20:]}"
                )
            return "⚠️ Gagal mengambil statistik."

        if cmd == "/help":
            lines = [f"🤖 *{settings.bot_name} — Perintah Tersedia*\n"]
            for command, desc in COMMANDS.items():
                lines.append(f"• `{command}` — {desc}")
            return "\n".join(lines)

        if cmd == "/ping":
            redis_ok = await memory_manager.ping()
            return (
                f"🏓 Pong!\n"
                f"├ Bot   : ✓ Online\n"
                f"└ Redis : {'✓ Connected' if redis_ok else '✗ Disconnected'}"
            )

        return ""

    async def _send_reply(
        self, client: NewAClient, event: MessageEv, text: str
    ) -> None:
        t0 = time.monotonic()
        try:
            await client.reply_message(text, event)
            elapsed = (time.monotonic() - t0) * 1000
            logger.debug(f"[Bot] ✓ Reply sent in {elapsed:.0f}ms")
            logger.debug("[Bot] ✓ Reply sent")
        except Exception as e:
            logger.error(f"[Bot] Failed to send reply: {e}")

    async def _send_typing(
        self, client: NewAClient, chat_jid: JID, is_typing: bool
    ) -> None:
        try:
            state = (
                ChatPresence.CHAT_PRESENCE_COMPOSING
                if is_typing else
                ChatPresence.CHAT_PRESENCE_PAUSED
            )
            await client.send_chat_presence(
                chat_jid, state, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT
            )
        except Exception as e:
            logger.debug(f"[Bot] Typing indicator failed (non-critical): {e}")

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self) -> None:
        logger.info(f"[Bot] Starting {settings.bot_name}...")
        logger.info(f"[Bot] Session: {settings.session_name}")
        logger.info("[Bot] Connecting to WhatsApp...")
        await self.client.connect()
        await self.client.idle()

    async def stop(self) -> None:
        """Graceful disconnect."""
        try:
            # Neonize tidak punya disconnect eksplisit yang clean,
            # idle() akan break ketika client di-close internal
            logger.info("[Bot] Stop requested")
        except Exception as e:
            logger.error(f"[Bot] Error during stop: {e}")