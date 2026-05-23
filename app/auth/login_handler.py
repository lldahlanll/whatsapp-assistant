# app/auth/login_handler.py
"""
Login & logout commands untuk multi-user mode.

Commands:
    /login email password  → fresh login dengan credential baru
    /login                  → quick re-login dengan credential tersimpan
    /logout                 → hapus session (credential masih tersimpan)
    /whoami                 → cek siapa yang login & sisa session

Security features:
- Verify credential ke IMAP/SMTP sebelum simpan
- Auto-cleanup invalid credential
- Force admin notification untuk login attempt dari non-whitelisted user
- Reminder ke user untuk hapus pesan password
"""
from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.auth.credential_store import UserCredential, credential_store
from app.auth.session_manager import session_manager
from app.auth.whitelist import whitelist
from app.email.client import (
    EmailAuthError,
    EmailConnectionError,
    ZimbraEmailClient,
)

if TYPE_CHECKING:
    from neonize.aioze.client import NewAClient


class LoginHandler:
    """
    Handle login/logout commands.

    Stateless — semua state di Redis via auth layer.
    Notifikasi admin di-inject via callback (avoid circular import dengan bot.py).
    """

    def __init__(self) -> None:
        # Optional callback untuk notify admin saat ada login attempt
        # Signature: async def(jid: str, name: str, message: str) -> None
        self._notify_admin_callback = None

    def set_admin_notify_callback(self, callback) -> None:
        """Set callback untuk DM admin saat ada non-whitelisted login attempt."""
        self._notify_admin_callback = callback

    # ── Public API ────────────────────────────────────────────

    async def handle(self, text: str, jid: str, push_name: str = "") -> str:
        """
        Route login-related commands.

        Args:
            text: Pesan user
            jid: JID user
            push_name: WhatsApp display name (untuk notif admin)

        Returns:
            Response message untuk dikirim ke user
        """
        cmd_lower = text.strip().lower()

        if cmd_lower.startswith("/login"):
            return await self._cmd_login(text, jid, push_name)

        if cmd_lower == "/logout":
            return await self._cmd_logout(jid)

        if cmd_lower == "/whoami":
            return await self._cmd_whoami(jid)

        return ""  # Bukan command kita

    # ── Command Implementations ───────────────────────────────

    async def _cmd_login(
        self,
        text: str,
        jid: str,
        push_name: str,
    ) -> str:
        """
        /login email password → fresh login
        /login                → quick re-login (pakai credential tersimpan)
        """
        # ── Check 1: Authorization ────────────────────────────
        is_admin = whitelist.is_admin(jid)
        is_whitelisted = await whitelist.is_authorized(jid)

        if not (is_admin or is_whitelisted):
            # Non-whitelisted user mencoba login
            await self._notify_admin_unauthorized(jid, push_name, text)
            return (
                "⚠️ *Akses ditolak*\n\n"
                "Nomor Anda belum diizinkan menggunakan bot ini.\n"
                "Silakan hubungi admin untuk request akses.\n\n"
                "💡 Admin sudah saya beritahu tentang request Anda."
            )

        # ── Check 2: Parse arguments ──────────────────────────
        parts = text.strip().split(maxsplit=2)

        if len(parts) == 1:
            # /login (tanpa argumen) → quick re-login
            return await self._quick_relogin(jid)

        if len(parts) != 3:
            return (
                "⚠️ *Format salah*\n\n"
                "Gunakan salah satu:\n"
                "• `/login email@vci.co.id password` — login fresh\n"
                "• `/login` (tanpa argumen) — quick re-login dengan credential tersimpan\n\n"
                "🗑️ *PENTING:* Setelah login, segera hapus pesan ini!"
            )

        _, email, password = parts
        email = email.strip().lower()

        # ── Check 3: Email format ─────────────────────────────
        if "@" not in email or "." not in email:
            return f"⚠️ Email tidak valid: `{email}`\nFormat: email@domain.com"

        # ── Check 4: Verify credential via IMAP ───────────────
        return await self._verify_and_save(jid, email, password, push_name)

    async def _quick_relogin(self, jid: str) -> str:
        """
        /login tanpa argumen — pakai credential tersimpan.
        Useful kalau session expired tapi credential masih ada.
        """
        existing_cred = await credential_store.get(jid)

        if existing_cred is None:
            return (
                "⚠️ *Belum ada credential tersimpan*\n\n"
                "Untuk login pertama kali, gunakan:\n"
                "`/login email@vci.co.id password`\n\n"
                "🗑️ *PENTING:* Setelah login, segera hapus pesan password!"
            )

        # Verify credential lama masih valid (password mungkin berubah di Zimbra)
        client = ZimbraEmailClient.for_user(existing_cred)

        try:
            test_result = await client.test_connection()
        except (EmailAuthError, EmailConnectionError) as e:
            logger.warning(
                f"[LoginHandler] Quick re-login failed for {jid}: {e}"
            )
            # Cleanup credential yang sudah invalid
            await credential_store.delete(jid)
            return (
                "⚠️ *Credential tersimpan tidak valid lagi*\n\n"
                "Mungkin password Zimbra Anda berubah.\n"
                "Silakan login ulang dengan password baru:\n"
                "`/login email@vci.co.id password`"
            )

        if not test_result.get("imap"):
            # IMAP gagal tapi tidak raise (kemungkinan auth)
            await credential_store.delete(jid)
            return (
                "⚠️ *Credential tidak valid lagi*\n"
                "Silakan login ulang: `/login email password`"
            )

        try:
            session = await session_manager.create(jid, existing_cred.email)
        except Exception as e:
            logger.error(
                f"[LoginHandler] Quick re-login session create failed for {jid}: {e}"
            )
            return (
                "⚠️ *Gagal membuat session*\n\n"
                "Credential masih valid, tapi Redis sementara bermasalah.\n"
                "Coba lagi: `/login` (tanpa argumen)"
            )

        logger.info(
            f"[LoginHandler] ✓ Quick re-login: {jid} → {existing_cred.email}"
        )

        return (
            f"✅ *Quick re-login berhasil!*\n\n"
            f"├ Email   : {existing_cred.email}\n"
            f"├ Session : aktif {session.remaining_human}\n"
            f"└ Status  : ✓ Credential masih valid\n\n"
            f"💡 Anda bisa langsung pakai `/email today`"
        )

    async def _verify_and_save(
        self,
        jid: str,
        email: str,
        password: str,
        push_name: str,
    ) -> str:
        """Verify kredensial ke Zimbra, simpan kalau valid, buat session."""
        # Buat temp credential untuk testing (jangan disimpan dulu)
        temp_cred = UserCredential(
            email=email,
            password=password,
            display_name=push_name or email,
        )

        client = ZimbraEmailClient.for_user(temp_cred)

        try:
            test_result = await client.test_connection()
        except EmailConnectionError as e:
            logger.error(f"[LoginHandler] Connection error for {jid}: {e}")
            return (
                "⚠️ *Tidak bisa connect ke server email*\n\n"
                "Server mungkin sedang down atau tidak bisa diakses.\n"
                "Coba lagi nanti, atau hubungi admin."
            )
        except EmailAuthError as e:
            logger.warning(
                f"[LoginHandler] Auth failed for {jid} ({email}): {e}"
            )
            return (
                "❌ *Login gagal*\n\n"
                "Email atau password salah.\n"
                "Pastikan kredensial Anda benar dan coba lagi.\n\n"
                "🗑️ *PENTING:* Hapus pesan password Anda!"
            )

        if not test_result.get("imap"):
            return (
                "❌ *Login IMAP gagal*\n\n"
                "Email atau password salah.\n"
                "Cek lagi kredensial Anda.\n\n"
                "🗑️ *PENTING:* Hapus pesan password Anda!"
            )

        # ── Simpan credential terenkripsi ─────────────────────
        cred_saved = await credential_store.save(jid, temp_cred)
        if not cred_saved:
            return "⚠️ Gagal simpan kredensial. Coba lagi nanti."

        # ── Buat session (rollback credential kalau gagal) ───
        try:
            session = await session_manager.create(jid, email)
        except Exception as e:
            await credential_store.delete(jid)
            logger.error(
                f"[LoginHandler] Session create failed, rolled back credential "
                f"for {jid}: {e}"
            )
            return (
                "⚠️ *Gagal membuat session*\n\n"
                "Kredensial tidak disimpan (rollback).\n"
                "Coba lagi sebentar: `/login email password`"
            )

        logger.info(
            f"[LoginHandler] ✓ Login success: {jid} → {email} "
            f"(session {session.remaining_human})"
        )

        smtp_status = "✓ OK" if test_result.get("smtp") else "✗ FAIL"
        smtp_warning = ""
        if not test_result.get("smtp"):
            smtp_warning = (
                "\n\n⚠️ *SMTP gagal* — Anda bisa baca email tapi tidak bisa kirim.\n"
                "Hubungi admin untuk cek konfigurasi SMTP."
            )

        return (
            f"✅ *Login berhasil!*\n\n"
            f"├ Email     : {email}\n"
            f"├ IMAP      : ✓ OK\n"
            f"├ SMTP      : {smtp_status}\n"
            f"└ Session   : aktif {session.remaining_human}"
            f"{smtp_warning}\n\n"
            f"🗑️ *PENTING:* Sekarang hapus pesan password Anda di atas!\n"
            f"Pesan password tetap visible di chat sampai Anda hapus."
        )

    async def _cmd_logout(self, jid: str) -> str:
        """
        /logout → hapus session tapi credential tetap ada.
        User bisa /login (tanpa argumen) untuk quick re-login.
        """
        had_session = await session_manager.is_active(jid)

        if not had_session:
            return "ℹ️ Anda belum login. Gunakan `/login email password`."

        await session_manager.delete(jid)
        logger.info(f"[LoginHandler] ✓ Logout: {jid}")

        return (
            "✅ *Logout berhasil*\n\n"
            "Session dihapus, tapi credential masih tersimpan.\n"
            "Untuk login ulang cepat, ketik `/login` saja (tanpa argumen).\n\n"
            "💡 Untuk hapus credential permanent, ketik `/logout permanent`"
        )

    async def _cmd_whoami(self, jid: str) -> str:
        """/whoami → cek status login user."""
        is_admin = whitelist.is_admin(jid)
        session = await session_manager.get(jid)
        cred_exists = await credential_store.exists(jid)

        lines = ["👤 *Status Akun*\n"]

        if is_admin:
            lines.append("├ Role         : 👑 Admin")
        elif await whitelist.is_authorized(jid):
            lines.append("├ Role         : ✓ Authorized User")
        else:
            lines.append("├ Role         : ✗ Not authorized")

        if session:
            lines.append(f"├ Login as     : {session.email}")
            lines.append(f"├ Session      : {session.remaining_human} tersisa")
            lines.append(f"└ Credential   : {'✓ Tersimpan' if cred_exists else '✗ Hilang'}")
        else:
            if cred_exists:
                lines.append("├ Status       : ⏰ Session expired")
                lines.append("└ Quick login  : ketik `/login` tanpa argumen")
            else:
                lines.append("├ Status       : 🔒 Belum login")
                lines.append("└ Login        : `/login email password`")

        return "\n".join(lines)

    # ── Helper: notify admin saat ada non-whitelisted attempt ─

    async def _notify_admin_unauthorized(
        self,
        jid: str,
        push_name: str,
        attempted_command: str,
    ) -> None:
        """Notify admin tentang user belum di-whitelist yang coba akses."""
        if self._notify_admin_callback is None:
            logger.debug(
                f"[LoginHandler] Unauthorized attempt from {jid}, "
                "but no admin notify callback registered"
            )
            return

        # Jangan kirim password ke admin — censor command
        cmd_safe = attempted_command.split()[0] if attempted_command else "/login"

        message = (
            f"🔔 *Login Attempt — Unauthorized User*\n\n"
            f"├ Nomor    : `{jid}`\n"
            f"├ Nama     : {push_name or 'Unknown'}\n"
            f"├ Command  : {cmd_safe}\n"
            f"└ Action   : User tidak ada di whitelist\n\n"
            f"💡 Untuk approve, ketik:\n"
            f"`/admin add {jid} {push_name or 'Nama'}`"
        )

        try:
            for admin_jid in whitelist.get_admin_jids():
                await self._notify_admin_callback(admin_jid, push_name, message)
            logger.info(
                f"[LoginHandler] Admin notified about unauthorized attempt: {jid}"
            )
        except Exception as e:
            logger.error(f"[LoginHandler] Failed to notify admin: {e}")


# Singleton — initialized di bot.py dengan callback
login_handler = LoginHandler()