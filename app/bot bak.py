# app/bot.py
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
from app.email.bot_handler import EmailCommandHandler
from app.email.client import EmailMessage
from app.email.scheduler import email_scheduler
from app.memory import memory_manager
from app.utils.locks import jid_lock_manager
from app.utils.stats import stats_tracker

COMMANDS = {
    "/reset":          "Hapus riwayat percakapan",
    "/stats":          "Lihat statistik percakapan",
    "/help":           "Tampilkan daftar perintah",
    "/ping":           "Cek bot aktif",
    "/email today":    "Rangkum email hari ini",
    "/email unread":   "Email belum dibaca",
    "/email summary":  "Rangkum email tanggal tertentu",
    "/email reply":    "Balas email dengan AI",
    "/email send":     "Kirim email baru",
    "/email ping":     "Test koneksi email",
}


class WhatsAppBot:
    def __init__(self) -> None:
        self.client = NewAClient(settings.session_db_path)
        self.bot_jid: str = ""
        self.bot_lid: str = ""
        self.bot_number: str = ""
        self._stop_event = asyncio.Event()

        # Email handler — stateful per-JID (simpan pending draft)
        self._email_handler = EmailCommandHandler()

        self._register_events()

    # ── Event registration ────────────────────────────────────

    def _register_events(self) -> None:
        @self.client.event(ConnectedEv)
        async def on_connected(client: NewAClient, event: ConnectedEv):
            try:
                me = await client.get_me()
                self.bot_jid = f"{me.JID.User}@{me.JID.Server}"
                self.bot_number = me.JID.User
                if hasattr(me, "LID") and me.LID and me.LID.User:
                    self.bot_lid = f"{me.LID.User}@{me.LID.Server}"
            except Exception as e:
                logger.warning(f"[Bot] Could not get bot JID: {e}")

            redis_ok = await memory_manager.ping()
            logger.info(f"[Bot] ✓ Connected as: {self.bot_jid}")
            logger.info(f"[Bot] LID: {self.bot_lid or '(none)'}")
            logger.info(f"[Bot] Bot number: {self.bot_number}")
            logger.info(f"[Bot] Bot name: {settings.bot_name}")
            logger.info(f"[Bot] Redis: {'✓ OK' if redis_ok else '✗ FAIL'}")

            # ── Start email scheduler setelah bot connected ───
            await self._start_email_scheduler(client)

        @self.client.event(DisconnectedEv)
        async def on_disconnected(client: NewAClient, event: DisconnectedEv):
            logger.warning("[Bot] ✗ Disconnected from WhatsApp")

        @self.client.event(MessageEv)
        async def on_message(client: NewAClient, event: MessageEv):
            asyncio.create_task(self._handle_message_safe(client, event))

    # ── Email Scheduler Setup ─────────────────────────────────

    async def _start_email_scheduler(self, client: NewAClient) -> None:
        """
        Setup dan start email polling scheduler.
        Notifikasi dikirim ke EMAIL_NOTIFY_JID yang dikonfigurasi di .env
        """
        if not settings.email_configured:
            logger.info("[Bot] Email not configured — scheduler skipped")
            return

        notify_jid_str = settings.email_notify_jid
        if not notify_jid_str:
            logger.info(
                "[Bot] EMAIL_NOTIFY_JID not set — "
                "email scheduler will run but no WA notifications"
            )

        async def _notify_new_emails(emails: list[EmailMessage]) -> None:
            """Callback: kirim notifikasi email baru ke WhatsApp."""
            if not notify_jid_str or not emails:
                return

            # Build pesan notifikasi
            lines = [f"🔔 *{len(emails)} email baru masuk!*\n"]
            for e in emails[:5]:  # Max 5 email per notifikasi
                status = "🔵" if not e.is_read else ""
                att = f" 📎" if e.attachments else ""
                lines.append(
                    f"{status} *{e.subject[:45]}*\n"
                    f"   Dari: {e.sender_email}{att}\n"
                    f"   {e.received_at.strftime('%H:%M')} | UID: `{e.uid}`"
                )

            if len(emails) > 5:
                lines.append(f"\n_...dan {len(emails) - 5} email lainnya_")

            lines.append("\n💡 Ketik `/email today` untuk ringkasan lengkap")
            message = "\n".join(lines)

            try:
                # Parse JID string ke proto JID
                target_jid = self._parse_jid(notify_jid_str)
                if target_jid:
                    await client.send_message(target_jid, message)
                    logger.info(
                        f"[Bot] ✓ Email notification sent: {len(emails)} emails"
                    )
            except Exception as e:
                logger.error(f"[Bot] Failed to send email notification: {e}")

        # Inject callback dan start
        email_scheduler.set_notify_callback(_notify_new_emails)
        await email_scheduler.start()
        logger.info(
            f"[Bot] ✓ Email scheduler started "
            f"(poll every {settings.email_poll_interval_seconds}s)"
        )

    # ── Message handler ───────────────────────────────────────

    async def _handle_message_safe(
        self, client: NewAClient, event: MessageEv
    ) -> None:
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

        if await memory_manager.is_rate_limited(sender_jid):
            logger.warning(f"[Bot] ⚠️ SPAM dari {sender_jid}, ignored")
            return

        await stats_tracker.track_message_received(chat_jid, is_group)

        if is_group and not self._should_reply_in_group(event, text):
            return

        try:
            async with jid_lock_manager.acquire(chat_jid, timeout=120.0):
                await self._process_message(
                    client, event, chat_jid, push_name, is_group, text
                )
        except asyncio.TimeoutError:
            logger.error(
                f"[Bot] Lock timeout for {chat_jid} — skip"
            )
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

        # ── Command handler ───────────────────────────────────
        if text.startswith("/"):
            chat_jid_proto = event.Info.MessageSource.Chat
            needs_typing = self._command_needs_typing(text)

            # Show typing untuk command yang butuh waktu (AI/IMAP/SMTP call)
            if needs_typing:
                await self._send_typing(client, chat_jid_proto, True)

            try:
                response = await self._handle_command(text, chat_jid)
            finally:
                if needs_typing:
                    await self._send_typing(client, chat_jid_proto, False)

            if response:
                await self._send_reply(client, event, self._format_md(response))
            return

        # ── AI generation ─────────────────────────────────────
        await memory_manager.add_message(chat_jid, "user", text)
        history = await memory_manager.get_history(chat_jid)

        chat_context = ChatContext(
            push_name=push_name,
            is_group=is_group,
            timezone_offset=7,
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

    @staticmethod
    def _command_needs_typing(text: str) -> bool:
        """
        Tentukan apakah command butuh typing indicator.

        Butuh typing (ada network/AI call):
        - /email today, unread, summary, detail   → IMAP fetch + AI summarize
        - /email reply                              → IMAP fetch + AI generate
        - /email confirm                            → SMTP send
        - /email send                               → AI generate + SMTP send
        - /email ping                               → IMAP+SMTP test
        - /ping                                     → Redis ping + breaker check
        - /stats                                    → Redis read

        Tidak butuh typing (instant):
        - /help                                     → static text
        - /reset                                    → 1x Redis delete (cepat)
        - /email cancel                             → in-memory dict delete
        - /email help                               → static text
        """
        cmd_lower = text.strip().lower()

        # Whitelist: command yang instant (response < 100ms biasanya)
        instant_commands = {
            "/help",
            "/reset",
            "/email cancel",
            "/email help",
        }

        # Cek exact match dengan instant commands
        first_two_words = " ".join(cmd_lower.split()[:2])
        if cmd_lower in instant_commands or first_two_words in instant_commands:
            return False

        # Default: anggap butuh typing (network/AI call)
        return True

    # ── Command Router ────────────────────────────────────────

    async def _handle_command(self, text: str, jid: str) -> str:
        """
        Route command ke handler yang tepat.
        Command /email → EmailCommandHandler
        Command lain   → handler lokal
        """
        cmd_lower = text.strip().lower()

        # ── Email commands → delegate ke EmailCommandHandler ──
        if cmd_lower.startswith("/email"):
            await stats_tracker.track_command("/email")
            return await self._email_handler.handle(text, jid)

        # ── Built-in commands ─────────────────────────────────
        cmd = cmd_lower.split()[0]
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
            return self._build_help_text()

        if cmd == "/ping":
            from app.ai.client import multi_client
            redis_ok = await memory_manager.ping()
            breaker_data = await multi_client.breaker_status()
            disabled_count = len(breaker_data)
            breaker_text = (
                f"⚠️ {disabled_count} model disabled"
                if disabled_count > 0
                else "✓ All models OK"
            )
            return (
                f"🏓 Pong!\n"
                f"├ Bot      : ✓ Online\n"
                f"├ Redis    : {'✓ Connected' if redis_ok else '✗ Disconnected'}\n"
                f"├ Models   : {breaker_text}\n"
                f"└ Email    : {'✓ Configured' if settings.email_configured else '– Not set'}"
            )

        return ""

    def _build_help_text(self) -> str:
        return (
            f"🤖 *{settings.bot_name} — Perintah Tersedia*\n\n"
            "*💬 Umum:*\n"
            "• `/reset` — hapus riwayat percakapan\n"
            "• `/stats` — statistik chat\n"
            "• `/ping` — cek status bot\n"
            "• `/help` — tampilkan perintah ini\n\n"
            "*📧 Email (Zimbra):*\n"
            "• `/email today` — rangkum email hari ini\n"
            "• `/email unread` — email belum dibaca\n"
            "• `/email summary 2026-04-29` — rangkum tanggal tertentu\n"
            "• `/email detail <uid>` — detail isi email\n"
            "• `/email reply <uid> <instruksi>` — draft balasan AI\n"
            "• `/email confirm` — kirim draft\n"
            "• `/email cancel` — batalkan draft\n"
            "• `/email send <to> | <subject> | <instruksi>` — email baru\n"
            "• `/email ping` — test koneksi Zimbra"
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
        if not jid_str:
            return False
        if jid_str == self.bot_jid or jid_str == self.bot_lid:
            return True
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

    @staticmethod
    def _parse_jid(jid_str: str) -> Optional[JID]:
        """
        Parse JID string ke proto JID untuk neonize send_message.
        Format: "628123456789@s.whatsapp.net"
        """
        try:
            user, server = jid_str.split("@")
            jid = JID()
            jid.User = user
            jid.Server = server
            return jid
        except Exception as e:
            logger.error(f"[Bot] Invalid JID format '{jid_str}': {e}")
            return None

    async def _send_reply(
        self, client: NewAClient, event: MessageEv, text: str
    ) -> None:
        t0 = time.monotonic()
        try:
            await client.reply_message(text, event)
            elapsed = (time.monotonic() - t0) * 1000
            logger.debug(f"[Bot] ✓ Reply sent in {elapsed:.0f}ms")
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
        logger.info("[Bot] Stop requested")
        await email_scheduler.stop()