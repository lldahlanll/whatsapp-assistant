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

# === Imports tambahan dari patch ===
from app.db.customer_db import customer_db
from app.db.audit_log import audit_log
from app.services.customer_lookup import customer_lookup
# ===================================

from app.ai import route_and_generate
from app.ai.prompts import ChatContext
from app.auth import (
    admin_handler,
    check_auth,
    AuthState,
    login_handler,
    whitelist,
)
from app.config import settings
from app.email import email_command_handler, validate_email_server_config
from app.memory import memory_manager
from app.utils.locks import jid_lock_manager
from app.utils.stats import stats_tracker
from app.email.scheduler import email_scheduler
from app.auth.rate_limiter import ai_rate_limiter


class WhatsAppBot:
    def __init__(self) -> None:
        self.client = NewAClient(settings.session_db_path)
        self.bot_jid: str = ""
        self.bot_lid: str = ""
        self.bot_number: str = ""
        self._stop_event = asyncio.Event()
        self._register_events()

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

            # === Tambahan inisialisasi DB dari patch ===
            if settings.customer_db_configured:
                try:
                    await customer_db.init()
                except Exception as e:
                    logger.error(f"[Bot] Customer DB init failed: {e}")
            # ===========================================

            redis_ok = await memory_manager.ping()
            email_config_ok = validate_email_server_config()
            admin_count = len(whitelist.get_admin_jids())

            logger.info(f"[Bot] ✓ Connected as: {self.bot_jid}")
            logger.info(f"[Bot] LID: {self.bot_lid or '(none)'}")
            logger.info(f"[Bot] Bot number: {self.bot_number}")
            logger.info(f"[Bot] Bot name: {settings.bot_name}")
            logger.info(f"[Bot] Redis: {'✓ OK' if redis_ok else '✗ FAIL'}")
            logger.info(
                f"[Bot] Email config: {'✓ OK' if email_config_ok else '✗ INCOMPLETE'}"
            )
            logger.info(f"[Bot] Admins configured: {admin_count}")

            login_handler.set_admin_notify_callback(
                self._make_admin_notify_callback(client)
            )
            logger.info("[Bot] Admin notify callback registered")

            # ── Start multi-user email scheduler ─────────────────────
            await self._start_email_scheduler(client)

        @self.client.event(DisconnectedEv)
        async def on_disconnected(client: NewAClient, event: DisconnectedEv):
            logger.warning("[Bot] ✗ Disconnected from WhatsApp")

        @self.client.event(MessageEv)
        async def on_message(client: NewAClient, event: MessageEv):
            asyncio.create_task(self._handle_message_safe(client, event))

    def _make_admin_notify_callback(self, client: NewAClient):
        async def notify_admin(admin_jid: str, push_name: str, message: str):
            try:
                target = self._parse_jid(admin_jid)
                if not target:
                    logger.error(f"[Bot] Could not parse admin JID: {admin_jid}")
                    return

                logger.info(
                    f"[Bot] Sending admin notif → "
                    f"User={target.User} Server={target.Server}"
                )
                await client.send_message(target, message)
                logger.info(f"[Bot] ✓ Notified admin {admin_jid}")
            except Exception as e:
                logger.error(f"[Bot] Failed to notify admin {admin_jid}: {e}")

        return notify_admin

    # [FIX]: Indentasi sudah dikembalikan ke level class agar tidak error
    async def _start_email_scheduler(self, client: NewAClient) -> None:
        """Start multi-user email scheduler dengan per-user notify callback."""
        if not settings.multi_user_configured:
            logger.info("[Bot] multi_user_configured=False — scheduler skipped")
            return

        async def _notify_user(
            jid: str,
            emails: list,
            error: str | None = None,
        ) -> None:
            target = self._parse_jid(jid)
            if not target:
                logger.error(f"[Bot] Could not parse JID for notify: {jid}")
                return

            if error == "auth_failed":
                msg = (
                    "⚠️ *Notifikasi email dinonaktifkan*\n\n"
                    "Password email kamu sudah tidak valid.\n"
                    "Silakan `/logout` lalu `/login` ulang dengan password terbaru."
                )
            elif not emails:
                return
            else:
                lines = [f"🔔 *{len(emails)} email baru!*\n"]
                for e in emails[:5]:
                    att = " 📎" if e.attachments else ""
                    lines.append(
                        f"🔵 *{e.subject[:45]}*\n"
                        f"   Dari: {e.sender_email}{att}\n"
                        f"   {e.received_at.strftime('%H:%M')} | UID: `{e.uid}`"
                    )
                if len(emails) > 5:
                    lines.append(f"\n_...dan {len(emails) - 5} lainnya_")
                lines.append("\n💡 `/email today` untuk ringkasan lengkap")
                msg = "\n".join(lines)

            try:
                await client.send_message(target, msg)
                logger.info(
                    f"[Bot] ✓ Email notify sent → {jid} ({len(emails)} emails)"
                )
            except Exception as e:
                logger.error(f"[Bot] Failed to send notify to {jid}: {e}")

        email_scheduler.set_notify_callback(_notify_user)
        await email_scheduler.start()
        logger.info(
            f"[Bot] ✓ Email scheduler started "
            f"(interval={settings.email_poll_interval_seconds}s)"
        )

    async def _handle_message_safe(self, client, event):
        try:
            await self._handle_message(client, event)
        except Exception as e:
            logger.error(f"[Bot] Unhandled error: {e}")
            logger.error(f"[Bot] Traceback:\n{traceback.format_exc()}")

    async def _handle_message(self, client, event):
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

        # --- TAMBAHAN KODE UNTUK MENDAPATKAN JID GRUP ---
        if is_group:
            logger.info(
                f"[Bot] 🆔 GROUP_JID={chat_jid} | sender={sender_jid} | name={push_name}"
            )
        # ------------------------------------------------

        if await memory_manager.is_rate_limited(sender_jid):
            logger.warning(f"[Bot] ⚠️ SPAM dari {sender_jid}, ignored")
            return

        await stats_tracker.track_message_received(chat_jid, is_group)

        if is_group and not self._should_reply_in_group(event, text):
            return

        # Per-USER lock (sender_jid) untuk multi-user isolation
        try:
            async with jid_lock_manager.acquire(sender_jid, timeout=120.0):
                await self._process_message(
                    client,
                    event,
                    sender_jid,
                    chat_jid,
                    push_name,
                    is_group,
                    text,
                )
        except asyncio.TimeoutError:
            logger.error(f"[Bot] Lock timeout for {sender_jid}")
            try:
                await self._send_reply(
                    client, event, "⚠️ Bot sedang sibuk, coba lagi sebentar."
                )
            except Exception:
                pass

    async def _process_message(
        self,
        client,
        event,
        sender_jid: str,
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

        if text.startswith("/"):
            chat_jid_proto = event.Info.MessageSource.Chat
            needs_typing = self._command_needs_typing(text)

            if needs_typing:
                await self._send_typing(client, chat_jid_proto, True)

            try:
                response = await self._handle_command(
                    text,
                    sender_jid=sender_jid,
                    chat_jid=chat_jid,
                    push_name=push_name,
                )
            finally:
                if needs_typing:
                    await self._send_typing(client, chat_jid_proto, False)

            if response:
                await self._send_reply(client, event, self._format_md(response))
            return

        # === Tambahan Customer Lookup dari patch ===
        # ── Customer Lookup (group sales only) ────────────────
        if is_group and chat_jid in settings.customer_lookup_groups_set:
            phones = customer_lookup.extract_phone_numbers(text)
            if phones:
                await self._handle_customer_lookup(
                    client=client,
                    event=event,
                    sender_jid=sender_jid,
                    chat_jid=chat_jid,
                    push_name=push_name,
                    phones=phones,
                )
                return  # skip AI conversation
        # ========================================================

        # ── AI conversation: PUBLIC tapi rate-limited ─────────
        is_privileged = (
            whitelist.is_admin(sender_jid)
            or await whitelist.is_authorized(sender_jid)
        )
        if not is_privileged:
            allowed, remaining = await ai_rate_limiter.check_and_consume(sender_jid)
            if not allowed:
                await self._send_reply(
                    client,
                    event,
                    self._format_md(
                        "⏳ *Limit tercapai*\n\n"
                        "Maaf, kamu sudah mencapai batas chat per jam.\n"
                        "Coba lagi nanti, atau hubungi admin untuk akses penuh."
                    ),
                )
                return
            # Optional: log untuk monitoring
            logger.debug(f"[Bot] Anonymous chat from {sender_jid}, {remaining} left")

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
            await self._send_reply(
                client,
                event,
                "⚠️ Maaf, lagi ada gangguan teknis. Coba lagi sebentar lagi ya.",
            )

    async def _handle_command(
        self,
        text: str,
        *,
        sender_jid: str,
        chat_jid: str,
        push_name: str,
    ) -> str:
        """
        sender_jid: identitas user (auth, login, admin).
        chat_jid  : ruang percakapan (memory AI — grup atau private).
        """
        cmd_lower = text.strip().lower()

        # Auth commands — per user
        if cmd_lower.startswith("/login") or cmd_lower in ("/logout", "/whoami"):
            await stats_tracker.track_command(cmd_lower.split()[0])
            return await login_handler.handle(text, sender_jid, push_name)

        # Admin commands
        if cmd_lower.startswith("/admin"):
            await stats_tracker.track_command("/admin")
            return await admin_handler.handle(text, sender_jid)

        # Email commands
        if cmd_lower.startswith("/email"):
            await stats_tracker.track_command("/email")

            auth = await check_auth(sender_jid, require_credential=True)
            if not auth.is_authorized:
                return auth.get_response_message()
            return await email_command_handler.handle(text, sender_jid)

        cmd = cmd_lower.split()[0]
        await stats_tracker.track_command(cmd)

        # Public commands
        if cmd == "/help":
            return self._build_help_text(sender_jid)

        if cmd == "/ping":
            return await self._cmd_ping()

        # Authenticated commands (whitelist per user)
        auth = await check_auth(sender_jid, require_credential=False)
        if not auth.is_authorized:
            return auth.get_response_message()

        # Memory per chat (grup = satu thread bersama; private = DM)
        if cmd == "/reset":
            ok = await memory_manager.clear_history(chat_jid)
            return (
                "🗑️ Riwayat percakapan berhasil dihapus."
                if ok
                else "⚠️ Gagal menghapus riwayat."
            )

        if cmd == "/stats":
            stats = await memory_manager.get_stats(chat_jid)
            if stats:
                return (
                    f"📊 *Statistik Percakapan*\n"
                    f"├ Pesan tersimpan : {stats['message_count']}/{stats['max_history']}\n"
                    f"├ TTL             : {stats['ttl_hours']} jam\n"
                    f"└ Chat ID         : ...{chat_jid[-20:]}"
                )
            return "⚠️ Gagal mengambil statistik."

        return ""

    async def _cmd_ping(self) -> str:
        from app.ai.client import multi_client

        redis_ok = await memory_manager.ping()
        breaker_data = await multi_client.breaker_status()
        disabled_count = len(breaker_data)
        breaker_text = (
            f"⚠️ {disabled_count} model disabled"
            if disabled_count > 0
            else "✓ All models OK"
        )
        email_status = "✓ Configured" if validate_email_server_config() else "✗ Not set"
        return (
            f"🏓 Pong!\n"
            f"├ Bot      : ✓ Online\n"
            f"├ Redis    : {'✓ Connected' if redis_ok else '✗ Disconnected'}\n"
            f"├ Models   : {breaker_text}\n"
            f"├ Email    : {email_status}\n"
            f"└ Mode     : 🔐 Multi-user"
        )

    def _build_help_text(self, jid: str) -> str:
        is_admin = whitelist.is_admin(jid)

        lines = [
            f"🤖 *{settings.bot_name} — Perintah*\n",
            "*🔐 Authentication:*",
            "• `/login email password` — login fresh",
            "• `/login` — quick re-login",
            "• `/logout` — logout (cred tetap)",
            "• `/whoami` — cek status\n",
            "*💬 Chat & Memory:*",
            "• `/reset` — hapus riwayat",
            "• `/stats` — statistik",
            "• `/ping` — status bot",
            "• `/help` — tampilkan ini\n",
            "*📧 Email (butuh login):*",
            "• `/email today` — rangkum hari ini",
            "• `/email unread` — belum dibaca",
            "• `/email summary <date>` — tanggal tertentu",
            "• `/email reply <uid> <instruksi>`",
            "• `/email send <to>|<subj>|<isi>`",
            "• `/email help` — semua command email",
        ]

        if is_admin:
            lines.extend(
                [
                    "\n*👑 Admin:*",
                    "• `/admin add <jid> <nama>`",
                    "• `/admin remove <jid>`",
                    "• `/admin list`",
                    "• `/admin logout <jid>`",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _command_needs_typing(text: str) -> bool:
        cmd_lower = text.strip().lower()

        instant_commands = {
            "/help",
            "/reset",
            "/whoami",
            "/logout",
            "/email cancel",
            "/email help",
            "/admin help",
            "/admin list",
        }

        first_two_words = " ".join(cmd_lower.split()[:2])
        if cmd_lower in instant_commands or first_two_words in instant_commands:
            return False
        return True

    @staticmethod
    def _strip_bot_mentions(
        text: str,
        bot_number: str = "",
        bot_lid_user: str = "",
    ) -> str:
        """
        Strip mention bot sendiri (PN atau LID) dari teks.

        WhatsApp render LID dengan split arbitrary, contoh:
          '71816903155883' bisa muncul sebagai '@+7 1816903155883'
        Pattern murni regex sulit handle ini, jadi pakai 2-step:
        1. Tangkap kandidat broadly (@ + apa saja yang seperti digit)
        2. Check digit-only-nya match bot ID atau tidak
        """
        if not text:
            return text

        bot_ids = [bid for bid in [bot_number, bot_lid_user] if bid]
        if not bot_ids:
            return text

        pattern = re.compile(r"@[+\d\s]+")

        def _replace_if_bot(match):
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            if not digits:
                return candidate
            for bid in bot_ids:
                if digits == bid or digits.endswith(bid) or bid.endswith(digits):
                    return ""
            return candidate

        cleaned = pattern.sub(_replace_if_bot, text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned

    def _extract_text(self, event: MessageEv) -> str:
        msg = event.Message
        raw = ""
        if msg.conversation:
            raw = msg.conversation.strip()
        elif msg.extendedTextMessage and msg.extendedTextMessage.text:
            raw = msg.extendedTextMessage.text.strip()
        elif msg.listResponseMessage and msg.listResponseMessage.title:
            raw = msg.listResponseMessage.title.strip()
        elif (
            msg.buttonsResponseMessage
            and msg.buttonsResponseMessage.selectedDisplayText
        ):
            raw = msg.buttonsResponseMessage.selectedDisplayText.strip()
        else:
            return ""
        bot_lid_user = (
            self.bot_lid.split("@")[0] if self.bot_lid else ""
        )
        return self._strip_bot_mentions(raw, self.bot_number, bot_lid_user)

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
            for j in ctx.mentionedJID or []:
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
        text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)
        text = re.sub(r"#{1,6}\s*(.*)", r"*\1*", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        return text

    @staticmethod
    def _parse_jid(jid_str: str) -> Optional[JID]:
        """
        Parse JID string ke proto JID untuk neonize send_message.

        Support format:
        - 628xxx@s.whatsapp.net  (standard WhatsApp)
        - 628xxx@c.us            (legacy contact)
        - 12345@lid              (LID / private number)

        Neonize JID protobuf butuh field:
        - User, Server (required)
        - RawAgent, Device, Integrator (default 0)
        """
        try:
            user, server = jid_str.split("@")
            if not user or not server:
                logger.error(f"[Bot] Empty user/server in JID: {jid_str}")
                return None

            jid = JID()
            jid.User = user
            jid.Server = server
            # Required fields oleh neonize protobuf — set default 0
            jid.RawAgent = 0
            jid.Device = 0
            jid.Integrator = 0
            return jid
        except Exception as e:
            logger.error(f"[Bot] Invalid JID format '{jid_str}': {e}")
            return None

    async def _send_reply(self, client, event, text: str) -> None:
        try:
            await client.reply_message(text, event)
        except Exception as e:
            logger.error(f"[Bot] Failed to send reply: {e}")

    async def _send_typing(self, client, chat_jid: JID, is_typing: bool) -> None:
        try:
            state = (
                ChatPresence.CHAT_PRESENCE_COMPOSING
                if is_typing
                else ChatPresence.CHAT_PRESENCE_PAUSED
            )
            await client.send_chat_presence(
                chat_jid, state, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT
            )
        except Exception as e:
            logger.debug(f"[Bot] Typing indicator failed: {e}")

    # === Method tambahan dari patch ===
    def _resolve_sender_pn(self, event) -> Optional[str]:
        """
        Resolve sender ke format PN (@s.whatsapp.net) untuk mention.
        WhatsApp mention butuh PN — @lid tidak akan render sebagai clickable.

        Strategi:
        1. Coba SenderAlt/PN field dari MessageSource (jika tersedia)
        2. Fallback: return None — kita akan reply tanpa mention
        """
        try:
            src = event.Info.MessageSource
            # whatsmeow expose PN di field bernama-mana saja, coba beberapa
            for fname in ("SenderAlt", "SenderPN", "PN"):
                alt = getattr(src, fname, None)
                if alt and getattr(alt, "User", None) and getattr(alt, "Server", None):
                    user = alt.User.split(":")[0]
                    server = alt.Server
                    if server in ("s.whatsapp.net", "c.us"):
                        return f"{user}@{server}"
            # Fallback: kalau Sender sendiri sudah PN, pakai itu
            sender_server = src.Sender.Server
            if sender_server in ("s.whatsapp.net", "c.us"):
                user = src.Sender.User.split(":")[0]
                return f"{user}@{sender_server}"
            return None
        except Exception as e:
            logger.debug(f"[Bot] _resolve_sender_pn failed: {e}")
            return None

    async def _send_with_mention(
        self,
        client,
        chat_jid_proto: JID,
        text: str,
        mention_jids: list[str],
    ) -> None:
        """
        Kirim pesan dengan mention yang benar-benar clickable.

        neonize: send_message dengan mentionedJID di contextInfo
        akan trigger notifikasi ke user yang di-mention.
        """
        try:
            # Convert string JIDs ke proto JID
            mentioned_protos = []
            for jid_str in mention_jids:
                proto = self._parse_jid(jid_str)
                if proto:
                    mentioned_protos.append(proto)

            # neonize NewAClient.send_message support kwarg mentioned_jid
            # Cek docs neonize Anda untuk signature persis — sintaks ini
            # bisa beda antar versi.
            if mentioned_protos:
                await client.send_message(
                    chat_jid_proto,
                    text,
                    mentioned_jid=mentioned_protos,
                )
            else:
                await client.send_message(chat_jid_proto, text)
        except TypeError:
            # Fallback kalau signature beda — kirim tanpa mention
            logger.warning(
                "[Bot] send_message tidak support mentioned_jid kwarg, "
                "fallback ke send tanpa mention"
            )
            await client.send_message(chat_jid_proto, text)
        except Exception as e:
            logger.error(f"[Bot] _send_with_mention failed: {e}")

    async def _handle_customer_lookup(
        self,
        *,
        client,
        event,
        sender_jid: str,
        chat_jid: str,
        push_name: str,
        phones: list[str],
    ) -> None:
        """Handle lookup customer dari group sales. Reply ke pesan asli."""
        if not settings.customer_db_configured:
            return

        chat_jid_proto = event.Info.MessageSource.Chat
        await self._send_typing(client, chat_jid_proto, True)

        try:
            messages: list[str] = []

            for phone_core in phones[:5]:
                t0 = time.monotonic()
                try:
                    records = await customer_lookup.lookup_by_phone(phone_core)
                    elapsed = (time.monotonic() - t0) * 1000

                    logger.info(
                        f"[CustomerLookup] {sender_jid} ({push_name}) "
                        f"→ '{phone_core}' | {len(records)} hits | "
                        f"{elapsed:.0f}ms"
                    )

                    # Audit fire-and-forget
                    asyncio.create_task(
                        audit_log.log(
                            requester_jid=sender_jid,
                            requester_name=push_name,
                            group_jid=chat_jid,
                            phone_searched=phone_core,
                            result_count=len(records),
                            elapsed_ms=elapsed,
                        )
                    )

                    msg = customer_lookup.format_results(phone_core, records)
                    messages.append(msg)

                except asyncio.TimeoutError:
                    messages.append(f"⏱️ Timeout cek `{phone_core}`")
                except Exception as e:
                    logger.error(f"[CustomerLookup] Error '{phone_core}': {e}")
                    messages.append(f"⚠️ Error DB saat cek `{phone_core}`")

            # Gabung jadi 1 reply (kalau banyak nomor)
            if len(messages) == 1:
                final_text = messages[0]
            else:
                final_text = "\n\n━━━━━━━━━━\n\n".join(messages)

            # Reply ke pesan asli — pakai _send_reply yang sudah proven jalan
            await self._send_reply(client, event, final_text)

        finally:
            await self._send_typing(client, chat_jid_proto, False)
    # ==================================

    async def start(self) -> None:
        logger.info(f"[Bot] Starting {settings.bot_name}...")
        logger.info(f"[Bot] Mode: 🔐 Multi-user")
        logger.info("[Bot] Connecting to WhatsApp...")
        await self.client.connect()
        await self.client.idle()

    # === Modifikasi stop() dari patch ===
    async def stop(self) -> None:
        logger.info("[Bot] Stop requested")
        await email_scheduler.stop()
        await customer_db.close()
    # ====================================