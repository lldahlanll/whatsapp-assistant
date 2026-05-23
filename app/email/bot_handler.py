# app/email/bot_handler.py
"""
Email command handler untuk multi-user bot.

Refactor dari single-user version:
- Setiap command WAJIB cek auth via middleware
- Credential di-fetch per command (stateless)
- EmailAuthError handling: invalidate session + prompt re-login
"""
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.auth.middleware import AuthResult,AuthState, check_auth
from app.auth.session_manager import session_manager
from app.email.agent import email_agent
from app.email.client import EmailAuthError, EmailMessage, local_day_bounds, local_email_now
from app.config import settings


class EmailCommandHandler:
    """
    Handle semua /email commands dengan auth check.

    Per-JID state (in-memory):
    - pending_drafts: draft reply yang menunggu konfirmasi
    """

    def __init__(self) -> None:
        # { jid: {"draft": str, "original_email": EmailMessage, "credential_email": str} }
        self._pending_drafts: dict[str, dict] = {}

    async def handle(self, text: str, jid: str) -> str:
        """Entry point untuk semua /email commands."""
        parts = text.strip().split(maxsplit=2)
        sub_cmd = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2] if len(parts) > 2 else ""

        # Help command tidak butuh auth
        if sub_cmd in ("help", ""):
            return self._cmd_help()

        # Semua command lain butuh auth
        auth = await check_auth(jid, require_credential=True)
        if not auth.is_authorized:
            return auth.get_response_message()

        # Routing dengan auth context
        handlers = {
            "today":    self._cmd_today,
            "summary":  self._cmd_summary,
            "unread":   self._cmd_unread,
            "detail":   self._cmd_detail,
            "reply":    self._cmd_reply,
            "confirm":  self._cmd_confirm,
            "cancel":   self._cmd_cancel,
            "send":     self._cmd_send,
            "ping":     self._cmd_ping,
            "notify":   self._cmd_notify,
        }

        handler = handlers.get(sub_cmd)
        if handler is None:
            return self._cmd_help()

        try:
            return await handler(args, jid, auth)
        except EmailAuthError as e:
            # Credential invalid → invalidate session, prompt re-login
            logger.warning(
                f"[EmailHandler] Credential invalid for {jid}, "
                f"invalidating session"
            )
            await session_manager.delete(jid)
            return (
                "🔐 *Credential tidak valid lagi*\n\n"
                "Mungkin password Zimbra Anda sudah berubah.\n"
                "Silakan login ulang:\n"
                "`/login email@vci.co.id password_baru`"
            )
        except Exception as e:
            logger.error(f"[EmailHandler] {sub_cmd} error: {e}")
            return f"⚠️ Error saat menjalankan `/email {sub_cmd}`: {str(e)[:100]}"

    # ── Commands ──────────────────────────────────────────────

    async def _cmd_today(self, args: str, jid: str, auth) -> str:
        since, until = local_day_bounds()
        return await email_agent.fetch_and_summarize(
            credential=auth.credential,
            since=since,
            until=until,
            date_label="hari ini",
        )

    async def _cmd_summary(self, args: str, jid: str, auth) -> str:
        if not args:
            return (
                "⚠️ Format: `/email summary 2026-04-29`\n"
                "Atau range: `/email summary 2026-04-01 2026-04-30`"
            )

        date_parts = args.strip().split()
        try:
            since = datetime.strptime(date_parts[0], "%Y-%m-%d")
            since = since.replace(hour=0, minute=0, second=0)

            if len(date_parts) >= 2:
                until = datetime.strptime(date_parts[1], "%Y-%m-%d")
                until = until.replace(hour=23, minute=59, second=59)
                label = f"{date_parts[0]} s/d {date_parts[1]}"
            else:
                until = since.replace(hour=23, minute=59, second=59)
                label = date_parts[0]

            return await email_agent.fetch_and_summarize(
                credential=auth.credential,
                since=since,
                until=until,
                date_label=label,
            )
        except ValueError:
            return "⚠️ Format tanggal salah. Gunakan: `YYYY-MM-DD`"

    async def _cmd_unread(self, args: str, jid: str, auth) -> str:
        # UNSEEN tidak dibatasi "hari ini" — unread kemarin/tahun lalu tetap relevan
        since = local_email_now() - timedelta(days=30)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)
        return await email_agent.fetch_and_summarize(
            credential=auth.credential,
            since=since,
            date_label="belum dibaca (30 hari terakhir)",
            unread_only=True,
        )

    async def _cmd_detail(self, args: str, jid: str, auth) -> str:
        uid = args.strip()
        if not uid:
            return "⚠️ Format: `/email detail <uid>`"
        return await email_agent.get_email_detail(
            credential=auth.credential,
            uid=uid,
        )

    async def _cmd_reply(self, args: str, jid: str, auth) -> str:
        if not args:
            return (
                "⚠️ Format: `/email reply <uid> <instruksi>`\n"
                "Contoh: `/email reply 42 balas: saya bisa hadir`"
            )

        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return "⚠️ Instruksi tidak boleh kosong."

        uid, instruction = parts[0].strip(), parts[1].strip()

        draft, original_email = await email_agent.draft_reply(
            credential=auth.credential,
            uid=uid,
            instruction=instruction,
        )

        if original_email is None:
            return draft  # Error message

        # Simpan pending draft DENGAN credential email untuk verify saat confirm
        # (mencegah user A confirm draft user B kalau ada bug routing)
        self._pending_drafts[jid] = {
            "draft": draft,
            "original_email": original_email,
            "credential_email": auth.credential.email,
        }

        return (
            f"📝 *Draft Balasan*\n"
            f"From    : {auth.credential.email}\n"
            f"Kepada  : {original_email.sender_email}\n"
            f"Re      : {original_email.subject}\n"
            f"{'─' * 30}\n"
            f"{draft}\n"
            f"{'─' * 30}\n"
            f"Kirim?\n"
            f"• `/email confirm` — kirim sekarang\n"
            f"• `/email cancel` — batalkan"
        )

    async def _cmd_confirm(self, args: str, jid: str, auth) -> str:
        pending = self._pending_drafts.get(jid)
        if not pending:
            return (
                "⚠️ Tidak ada draft yang menunggu konfirmasi.\n"
                "Gunakan `/email reply <uid> <instruksi>` dulu."
            )

        # Safety: pastikan credential sekarang sama dengan saat draft dibuat
        # (mencegah edge case kalau user logout-login dengan akun beda)
        if pending["credential_email"] != auth.credential.email:
            del self._pending_drafts[jid]
            return (
                "⚠️ *Draft di-cancel*\n\n"
                "Anda login dengan akun yang berbeda dari saat draft dibuat.\n"
                "Silakan buat draft baru dengan akun saat ini."
            )

        original_email = pending["original_email"]
        draft = pending["draft"]

        # Clear pending SEBELUM send
        del self._pending_drafts[jid]

        success = await email_agent.send_reply(
            credential=auth.credential,
            original_email=original_email,
            draft_body=draft,
        )

        if success:
            return (
                f"✅ *Email berhasil dikirim!*\n"
                f"├ Dari   : {auth.credential.email}\n"
                f"├ Kepada : {original_email.sender_email}\n"
                f"└ Subjek : Re: {original_email.subject}"
            )
        return "⚠️ Gagal mengirim email. Cek koneksi dan coba lagi."

    async def _cmd_cancel(self, args: str, jid: str, auth) -> str:
        if jid in self._pending_drafts:
            del self._pending_drafts[jid]
            return "🗑️ Draft balasan dibatalkan."
        return "ℹ️ Tidak ada draft yang sedang pending."

    async def _cmd_send(self, args: str, jid: str, auth) -> str:
        if not args or "|" not in args:
            return (
                "⚠️ Format:\n"
                "`/email send <to> | <subject> | <instruksi isi>`\n\n"
                "Contoh:\n"
                "`/email send budi@co.com | Meeting | minta konfirmasi meeting besok`"
            )

        try:
            parts = [p.strip() for p in args.split("|", 2)]
            if len(parts) < 3:
                raise ValueError("Kurang dari 3 bagian")

            to_raw, subject, instruction = parts
            to_list = [e.strip() for e in to_raw.split(",") if e.strip()]

            if not to_list:
                return "⚠️ Alamat tujuan tidak valid."

            body, sent = await email_agent.compose_and_send(
                credential=auth.credential,
                to=to_list,
                subject=subject,
                instruction=instruction,
                auto_send=True,
            )

            if sent:
                return (
                    f"✅ *Email berhasil dikirim!*\n"
                    f"├ Dari    : {auth.credential.email}\n"
                    f"├ Kepada  : {', '.join(to_list)}\n"
                    f"├ Subjek  : {subject}\n"
                    f"└ Preview : {body[:150]}..."
                )
            return f"⚠️ Gagal kirim email.\n\nDraft yang digenerate:\n{body[:300]}"

        except ValueError as e:
            return f"⚠️ Format salah: {e}"

    async def _cmd_ping(self, args: str, jid: str, auth) -> str:
        return await email_agent.ping(credential=auth.credential)
    
    async def _cmd_notify(self, args: str, jid: str, auth: "AuthResult") -> str:
        """
        /email notify on   → opt-in notifikasi email baru
        /email notify off  → opt-out
        /email notify      → cek status
        """
        from app.email.notify_manager import notify_opt_in_manager
        from app.email.scheduler import email_scheduler

        sub = args.strip().lower()

        if sub == "on":
            # Reset last_check ke sekarang agar tidak flood email lama
            await email_scheduler.reset_last_check(jid)
            await notify_opt_in_manager.enable(jid)
            return (
                "🔔 *Notifikasi email diaktifkan!*\n\n"
                "Saya akan kirim pesan WhatsApp saat ada email baru masuk.\n"
                f"📡 Cek setiap {settings.email_poll_interval_seconds // 60} menit.\n\n"
                "Untuk matikan: `/email notify off`"
            )

        elif sub == "off":
            await notify_opt_in_manager.disable(jid)
            return (
                "🔕 *Notifikasi email dimatikan.*\n\n"
                "Kamu tetap bisa cek manual dengan `/email today`."
            )

        else:
            # Status check
            is_on = await notify_opt_in_manager.is_enabled(jid)
            status = "🟢 *Aktif*" if is_on else "🔴 *Tidak aktif*"
            interval_min = settings.email_poll_interval_seconds // 60
            return (
                f"📬 *Status Notifikasi Email*\n\n"
                f"Status   : {status}\n"
                f"Interval : setiap {interval_min} menit\n\n"
                f"Perintah:\n"
                f"  `/email notify on`  → aktifkan\n"
                f"  `/email notify off` → matikan"
            )

    def _cmd_help(self) -> str:
        return (
            "📧 *Email Commands*\n\n"
            "*🔐 Login wajib dulu:*\n"
            "• `/login email@vci.co.id password`\n\n"
            "*📥 Baca Email:*\n"
            "• `/email today` — rangkum email hari ini\n"
            "• `/email unread` — email belum dibaca\n"
            "• `/email summary 2026-04-29` — tanggal tertentu\n"
            "• `/email summary 2026-04-01 2026-04-30` — range\n"
            "• `/email detail <uid>` — detail isi email\n\n"
            "*✉️ Kirim & Balas:*\n"
            "• `/email reply <uid> <instruksi>` — draft balasan\n"
            "• `/email confirm` — kirim draft\n"
            "• `/email cancel` — batalkan draft\n"
            "• `/email send <to> | <subject> | <instruksi>` — email baru\n\n"
            "*🔧 Lainnya:*\n"
            "• `/email ping` — test koneksi Zimbra\n"
            "• `/whoami` — cek status login Anda"
        )


# Singleton
email_command_handler = EmailCommandHandler()