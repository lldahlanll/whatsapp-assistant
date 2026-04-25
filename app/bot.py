import asyncio
import os
import traceback
import time
import re
from loguru import logger

from neonize.aioze.client import NewAClient
from neonize.aioze.events import (
    ConnectedEv,
    MessageEv,
    DisconnectedEv,
)

from app.ai import route_and_generate
from app.memory import memory_manager
from app.utils.logger import setup_logger
from app.utils.stats import stats_tracker
from neonize.utils.enum import ChatPresence, ChatPresenceMedia
from neonize.proto.Neonize_pb2 import JID
from neonize.utils import build_jid

setup_logger()

# ── Config ────────────────────────────────────────────────────
SESSION_NAME = os.getenv("SESSION_NAME", "mybot_session")
BOT_NAME     = os.getenv("BOT_NAME", "AI Bot")
DB_PATH = f"data/sessions/{SESSION_NAME}.db"

COMMANDS = {
    "/reset": "Hapus riwayat percakapan",
    "/stats": "Lihat statistik percakapan",
    "/help" : "Tampilkan daftar perintah",
    "/ping" : "Cek bot aktif",
}


class WhatsAppBot:

    def __init__(self):
        self.client  = NewAClient(SESSION_NAME)
        self.client = NewAClient(DB_PATH)
        self.bot_jid = ""
        self._register_events()

    def _register_events(self):

        @self.client.event(ConnectedEv)
        async def on_connected(client: NewAClient, event: ConnectedEv):
            try:
                me = await client.get_me()
                self.bot_jid = f"{me.JID.User}@{me.JID.Server}"
            except Exception:
                self.bot_jid = ""
                logger.warning("[Bot] Could not get bot JID")

            logger.info(f"[Bot] ✓ Connected as: {self.bot_jid}")
            logger.info(f"[Bot] Bot name: {BOT_NAME}")
            redis_ok = await memory_manager.ping()
            logger.info(f"[Bot] Redis: {'✓ Connected' if redis_ok else '✗ Failed'}")

        @self.client.event(DisconnectedEv)
        async def on_disconnected(client: NewAClient, event: DisconnectedEv):
            logger.warning("[Bot] ✗ Disconnected from WhatsApp")

        @self.client.event(MessageEv)
        async def on_message(client: NewAClient, event: MessageEv):
            await self._handle_message(client, event)

    # ── Message Handler ───────────────────────────────────────

    async def _handle_message(self, client: NewAClient, event: MessageEv):
        try:
            source     = event.Info.MessageSource
            is_from_me = source.IsFromMe
            is_group   = source.IsGroup

            # Abaikan pesan dari bot sendiri
            if is_from_me:
                return

            # Ekstrak teks pesan
            text = self._extract_text(event)
            if not text:
                return

            # Ekstrak JID — User@Server
            sender_jid = f"{source.Sender.User}@{source.Sender.Server}"
            chat_jid   = f"{source.Chat.User}@{source.Chat.Server}"
            memory_jid = chat_jid

            logger.info(
                f"[Bot] {'GROUP' if is_group else 'PRIVATE'} | "
                f"From: {sender_jid} | "
                f"Text: {text[:60]}{'...' if len(text) > 60 else ''}"
            )

            # ── Pengecekan SPAM (Rate Limit) ─────────────
            is_spam = await memory_manager.is_rate_limited(sender_jid, limti=3, window_seconds=10)
            if is_spam:
                logger.warning(f"[Bot] ⚠️ SPAM TERDETEKSI dari {sender_jid}. Pesan diabaikan.")
                return # Langsung stop eksekusi, abaikan pesan ini

            await stats_tracker.track_message_received(chat_jid, is_group)
            # Filter grup — hanya balas kalau di-mention atau di-reply
            if is_group and not self._should_reply_in_group(event, text):
                return

            memory_jid = chat_jid

            await memory_manager.save_meta(
                jid=memory_jid,
                name=chat_jid,
                is_group=is_group,
            )

            # Handle command
            if text.startswith("/"):
                response = await self._handle_command(text, memory_jid)
                if response:
                    formatted_response = self.format_for_whatsapp(response)
                    await self._send_reply(client, event, formatted_response)
                    return

            # ── Generate AI response ──────────────────────────────
            await memory_manager.add_message(memory_jid, "user", text)
            messages = await memory_manager.get_history(memory_jid)

            # Mulai typing indicator
            await self._send_typing(client, source.Chat, True)

            logger.info("[Bot] Generating response...")
            t_start = time.monotonic()
            response, model_used = await route_and_generate(messages, text)
            t_elapsed = (time.monotonic() - t_start) * 1000

            # Stop typing indicator
            await self._send_typing(client, source.Chat, False)

            if response:
                # [TRACK] Response Sukses
                await stats_tracker.track_response(model_used, True, t_elapsed)
                await memory_manager.add_message(memory_jid, "assistant", response)
                
                logger.info(f"[Bot] ✓ {model_used} replied ({len(response)} chars, {t_elapsed:.0f}ms)")
                formatted_response = self.format_for_whatsapp(response)
                await self._send_reply(client, event, formatted_response)
            else:
                # [TRACK] Response Gagal
                await stats_tracker.track_response("none", False, t_elapsed)
                logger.error("[Bot] All models failed")
                await self._send_reply(
                    client, event,
                    "⚠️ Maaf, saya sedang tidak bisa menjawab. Coba lagi sebentar lagi."
                )

        except Exception as e:
            logger.error(f"[Bot] Unhandled error: {e}")
            logger.error(f"[Bot] Traceback:\n{traceback.format_exc()}")

    # ── Helper: Ekstrak Teks ──────────────────────────────────

    def _extract_text(self, event: MessageEv) -> str:
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

    # ── Helper: Filter Grup ───────────────────────────────────

    def _should_reply_in_group(self, event: MessageEv, text: str) -> bool:
        # Cek mention nomor bot di teks (@628xxx)
        if self.bot_jid:
            bot_number = self.bot_jid.split("@")[0]
            if f"@{bot_number}" in text:
                return True

        # Cek reply ke pesan bot
        msg = event.Message
        if msg.extendedTextMessage:
            ctx = msg.extendedTextMessage.contextInfo
            if ctx and ctx.participant:
                p = ctx.participant
                participant_jid = f"{p.User}@{p.Server}"
                if participant_jid == self.bot_jid:
                    return True

        return False

    def format_for_whatsapp(self, text: str) -> str:
        # Ubah **teks** menjadi *teks*
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        # Ubah header ### Header menjadi *Header*
        text = re.sub(r'#{1,6}\s*(.*)', r'*\1*', text)
        # Ubah link [text](url) menjadi text (url)
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1 (\2)', text)
        return text

    # ── Helper: Handle Command ────────────────────────────────

    async def _handle_command(self, text: str, memory_jid: str) -> str:
        cmd = text.strip().lower().split()[0]

        await stats_tracker.track_command(cmd)

        if cmd == "/reset":
            success = await memory_manager.clear_history(memory_jid)
            return (
                "🗑️ Riwayat percakapan berhasil dihapus. Mulai dari awal!"
                if success else
                "⚠️ Gagal menghapus riwayat. Coba lagi."
            )

        elif cmd == "/stats":
            stats = await memory_manager.get_stats(memory_jid)
            if stats:
                return (
                    f"📊 *Statistik Percakapan*\n"
                    f"├ Pesan tersimpan : {stats['message_count']}/{stats['max_history']}\n"
                    f"├ TTL             : {stats['ttl_hours']} jam tersisa\n"
                    f"└ Chat ID         : ...{memory_jid[-20:]}"
                )
            return "⚠️ Gagal mengambil statistik."

        elif cmd == "/help":
            lines = [f"🤖 *{BOT_NAME} — Perintah Tersedia*\n"]
            for command, desc in COMMANDS.items():
                lines.append(f"• `{command}` — {desc}")
            return "\n".join(lines)

        elif cmd == "/ping":
            redis_ok = await memory_manager.ping()
            return (
                f"🏓 Pong!\n"
                f"├ Bot   : ✓ Online\n"
                f"└ Redis : {'✓ Connected' if redis_ok else '✗ Disconnected'}"
            )

        return ""

    # ── Helper: Send Reply ────────────────────────────────────

    async def _send_reply(self, client: NewAClient, event: MessageEv, text: str):
        try:
            await client.reply_message(text, event)
            logger.debug("[Bot] ✓ Reply sent")
        except Exception as e:
            logger.error(f"[Bot] Failed to send reply: {e}")

    # ── Send: Typing ────────────────────────────────────
    async def _send_typing(self, client: NewAClient, chat_jid: JID, is_typing: bool): # <-- Ganti tipe data jadi JID
        """
        Kirim typing indicator ke chat.
        """
        status_text = "START TYPING" if is_typing else "STOP TYPING"
        
        try:
            logger.info(f"[Bot] Mencoba mengirim status {status_text}")
                
            state = (
                ChatPresence.CHAT_PRESENCE_COMPOSING   # typing...
                if is_typing else
                ChatPresence.CHAT_PRESENCE_PAUSED       # stop typing
            )

            await client.send_chat_presence(
                chat_jid,  # <-- Langsung gunakan objek JID utuh
                state,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
            
            logger.info(f"[Bot] ✓ Berhasil mengirim status {status_text}")

        except Exception as e:
            logger.error(f"[Bot] ✗ GAGAL mengirim typing indicator: {e}")
            logger.error(f"[Bot] Traceback Error Typing:\n{traceback.format_exc()}")

    # ── Start ─────────────────────────────────────────────────

    async def start(self):
        logger.info(f"[Bot] Starting {BOT_NAME}...")
        logger.info(f"[Bot] Session: {SESSION_NAME}")
        logger.info("[Bot] Connecting to WhatsApp...")
        await self.client.connect()
        await self.client.idle()