# app/auth/admin_handler.py
"""
Admin commands untuk multi-user mode.

Commands:
    /admin add <jid> <nama>    → tambah user ke whitelist
    /admin remove <jid>         → hapus user (auto-cleanup session+cred)
    /admin list                 → list semua user + session aktif
    /admin logout <jid>         → force logout user (cabut session)
    /admin help                 → bantuan

Authorization:
    Hanya JID yang ada di ADMIN_JIDS (.env) yang bisa pakai.
"""
import time
from datetime import datetime
from typing import Optional

from loguru import logger

from app.auth.credential_store import credential_store
from app.auth.middleware import cleanup_user
from app.auth.session_manager import session_manager
from app.auth.whitelist import whitelist


class AdminHandler:
    """
    Handle /admin commands. Hanya admin yang bisa execute.
    """

    async def handle(self, text: str, jid: str) -> str:
        """
        Entry point untuk /admin commands.

        Args:
            text: Pesan user
            jid: JID user

        Returns:
            Response message
        """
        # ── Authorization check ───────────────────────────────
        if not whitelist.is_admin(jid):
            logger.warning(
                f"[AdminHandler] Non-admin {jid} tried admin command: {text}"
            )
            return (
                "⛔ *Akses ditolak*\n\n"
                "Command `/admin` hanya bisa digunakan oleh admin."
            )

        # ── Parse command ─────────────────────────────────────
        parts = text.strip().split(maxsplit=2)
        sub_cmd = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2] if len(parts) > 2 else ""

        handlers = {
            "add":     self._cmd_add,
            "remove":  self._cmd_remove,
            "list":    self._cmd_list,
            "logout":  self._cmd_logout,
            "help":    self._cmd_help,
        }

        handler = handlers.get(sub_cmd, self._cmd_help)
        try:
            return await handler(args, jid)
        except Exception as e:
            logger.error(f"[AdminHandler] {sub_cmd} error: {e}")
            return f"⚠️ Error: {str(e)[:100]}"

    # ── Command Implementations ───────────────────────────────

    async def _cmd_add(self, args: str, admin_jid: str) -> str:
        """
        /admin add <jid> <nama>

        Format JID:
        - 6281234567890@s.whatsapp.net (full)
        - 6281234567890 (auto-append @s.whatsapp.net)
        """
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return (
                "⚠️ *Format salah*\n\n"
                "Gunakan: `/admin add <jid> <nama>`\n\n"
                "Contoh:\n"
                "• `/admin add 628123456789 Budi`\n"
                "• `/admin add 628123456789@s.whatsapp.net Budi Santoso`"
            )

        target_jid_raw, name = parts[0].strip(), parts[1].strip()

        # Normalisasi JID — auto-append suffix kalau belum ada
        target_jid = self._normalize_jid(target_jid_raw)
        if not target_jid:
            return f"⚠️ Format JID tidak valid: `{target_jid_raw}`"

        # Cek apakah sudah di-whitelist
        if await whitelist.is_authorized(target_jid):
            return f"ℹ️ User `{target_jid}` sudah ada di whitelist."

        # Add
        added = await whitelist.add(target_jid, name, admin_jid)
        if not added:
            return "⚠️ Gagal menambahkan user. Cek log."

        return (
            f"✅ *User ditambahkan ke whitelist*\n\n"
            f"├ Nama  : {name}\n"
            f"├ JID   : `{target_jid}`\n"
            f"└ Oleh  : Admin\n\n"
            f"💡 User bisa langsung /login dari nomor tersebut."
        )

    async def _cmd_remove(self, args: str, admin_jid: str) -> str:
        """
        /admin remove <jid>
        Auto-cleanup: hapus session + credential + whitelist.
        """
        target_jid_raw = args.strip()
        if not target_jid_raw:
            return "⚠️ Format: `/admin remove <jid>`"

        target_jid = self._normalize_jid(target_jid_raw)
        if not target_jid:
            return f"⚠️ Format JID tidak valid: `{target_jid_raw}`"

        # Tidak boleh hapus admin (admin di .env, bukan whitelist)
        if whitelist.is_admin(target_jid):
            return (
                "⛔ Tidak bisa hapus admin via command ini.\n"
                "Admin diatur lewat `ADMIN_JIDS` di `.env`."
            )

        # Cek apakah user ada
        if not await whitelist.is_authorized(target_jid):
            return f"ℹ️ User `{target_jid}` tidak ada di whitelist."

        # Auto-cleanup semua data
        result = await cleanup_user(target_jid)

        cleanup_summary = []
        if result["session"]:
            cleanup_summary.append("✓ Session dihapus")
        if result["credential"]:
            cleanup_summary.append("✓ Credential dihapus")
        if result["whitelist"]:
            cleanup_summary.append("✓ Whitelist dihapus")

        summary_text = "\n".join(f"  {s}" for s in cleanup_summary)

        return (
            f"✅ *User dihapus*\n\n"
            f"├ JID  : `{target_jid}`\n"
            f"└ Cleanup:\n{summary_text}\n\n"
            f"User tidak bisa pakai bot lagi sampai admin tambahkan ulang."
        )

    async def _cmd_list(self, args: str, admin_jid: str) -> str:
        """/admin list → tampilkan whitelist + session aktif."""
        users = await whitelist.list_users()
        active_sessions = await session_manager.list_active()
        admin_jids = whitelist.get_admin_jids()

        # Build session lookup untuk efficient join
        session_by_jid = {s.jid: s for s in active_sessions}

        lines = []
        lines.append(f"👥 *Authorized Users*\n")

        # Admin section
        lines.append(f"*👑 Admins ({len(admin_jids)}):*")
        for admin_j in sorted(admin_jids):
            session = session_by_jid.get(admin_j)
            cred_exists = await credential_store.exists(admin_j)

            status = self._format_user_status(session, cred_exists)
            lines.append(f"  • `{admin_j}` {status}")

        # Whitelisted users section
        lines.append(f"\n*✓ Whitelist Users ({len(users)}):*")
        if not users:
            lines.append("  _(belum ada user di whitelist)_")
        else:
            for u in users:
                session = session_by_jid.get(u.jid)
                cred_exists = await credential_store.exists(u.jid)

                status = self._format_user_status(session, cred_exists)
                added_date = datetime.fromtimestamp(u.added_at).strftime("%Y-%m-%d")

                lines.append(
                    f"  • *{u.display_name}* {status}\n"
                    f"      `{u.jid}`\n"
                    f"      _added {added_date}_"
                )

        # Stats footer
        total_active = len(active_sessions)
        lines.append(
            f"\n*📊 Stats:*\n"
            f"  • Total authorized: {len(users) + len(admin_jids)}\n"
            f"  • Active sessions:  {total_active}"
        )

        return "\n".join(lines)

    async def _cmd_logout(self, args: str, admin_jid: str) -> str:
        """
        /admin logout <jid>
        Cabut session paksa (credential tetap ada).
        Berbeda dari /admin remove yang hapus semua.
        """
        target_jid_raw = args.strip()
        if not target_jid_raw:
            return "⚠️ Format: `/admin logout <jid>`"

        target_jid = self._normalize_jid(target_jid_raw)
        if not target_jid:
            return f"⚠️ Format JID tidak valid: `{target_jid_raw}`"

        # Cek session ada
        if not await session_manager.is_active(target_jid):
            return f"ℹ️ User `{target_jid}` tidak punya session aktif."

        # Hapus session saja (credential tetap)
        await session_manager.delete(target_jid)
        logger.info(
            f"[AdminHandler] Admin {admin_jid} forced logout: {target_jid}"
        )

        return (
            f"✅ *Session dicabut*\n\n"
            f"├ User : `{target_jid}`\n"
            f"└ Status: Session dihapus, credential masih ada\n\n"
            f"User harus /login lagi untuk pakai bot.\n"
            f"Quick re-login (`/login` tanpa argumen) tetap bisa."
        )

    async def _cmd_help(self, args: str, admin_jid: str) -> str:
        """/admin help."""
        return (
            "👑 *Admin Commands*\n\n"
            "*👤 User Management:*\n"
            "• `/admin add <jid> <nama>` — tambah user\n"
            "• `/admin remove <jid>` — hapus user (cleanup all data)\n"
            "• `/admin logout <jid>` — cabut session (cred masih ada)\n"
            "• `/admin list` — list semua user & session aktif\n\n"
            "*Format JID:*\n"
            "• `628123456789` (auto-append @s.whatsapp.net)\n"
            "• `628123456789@s.whatsapp.net` (full)\n\n"
            "*Contoh:*\n"
            "```\n"
            "/admin add 628123456789 Budi Santoso\n"
            "/admin remove 628123456789\n"
            "/admin logout 628123456789\n"
            "/admin list\n"
            "```"
        )

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize_jid(raw: str) -> Optional[str]:
        """
        Normalisasi JID input.
        - "628123456789" → "628123456789@s.whatsapp.net"
        - "628123456789@s.whatsapp.net" → unchanged
        - "+628123456789" → "628123456789@s.whatsapp.net"
        - "0812..." → reject (Indonesian local format, bot pakai international)
        """
        raw = raw.strip().replace(" ", "").replace("+", "").replace("-", "")

        # Reject local format (021..., 0812...)
        if raw.startswith("0"):
            return None

        # Reject angka kependekan
        if "@" not in raw and not raw.isdigit():
            return None

        if "@" not in raw:
            # Append default WhatsApp suffix
            return f"{raw}@s.whatsapp.net"

        # Sudah ada @, validate format dasar
        parts = raw.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None

        return raw

    @staticmethod
    def _format_user_status(session, cred_exists: bool) -> str:
        """Format status indicator untuk list view."""
        if session and session.is_active:
            return f"🟢 (active, {session.remaining_human})"
        if cred_exists:
            return "🟡 (offline, can quick re-login)"
        return "⚪ (never logged in)"


# Singleton
admin_handler = AdminHandler()