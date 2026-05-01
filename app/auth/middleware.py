# app/auth/middleware.py
"""
Auth middleware untuk multi-user mode.

Centralized auth check — dipakai oleh email_bot_handler dan command lain
yang butuh kredensial user.

Three-step verification:
1. Whitelist check    → JID boleh akses bot?
2. Session check      → user sudah login & belum expired?
3. Credential fetch   → ambil decrypted credential

Returns enum yang jelas — caller tinggal handle response per state.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger

from app.auth.credential_store import UserCredential, credential_store
from app.auth.session_manager import Session, session_manager
from app.auth.whitelist import whitelist


class AuthState(Enum):
    """Hasil pengecekan auth untuk satu JID."""
    AUTHORIZED = "authorized"           # ✓ Bisa pakai bot
    NOT_WHITELISTED = "not_whitelisted" # User belum di-add admin
    NOT_LOGGED_IN = "not_logged_in"     # Whitelisted tapi belum /login
    SESSION_EXPIRED = "session_expired" # Session sudah lewat 8 jam
    NO_CREDENTIAL = "no_credential"     # Edge case: session ada, cred hilang


@dataclass
class AuthResult:
    """Hasil lengkap auth check, siap dipakai di handler."""
    state: AuthState
    session: Optional[Session] = None
    credential: Optional[UserCredential] = None

    @property
    def is_authorized(self) -> bool:
        return self.state == AuthState.AUTHORIZED

    def get_response_message(self) -> str:
        """
        Generate response message berdasarkan state.
        Dipakai di handler kalau auth gagal.
        """
        messages = {
            AuthState.NOT_WHITELISTED: (
                "⚠️ *Akses ditolak*\n\n"
                "Nomor Anda belum diizinkan menggunakan bot ini.\n"
                "Silakan hubungi admin untuk request akses."
            ),
            AuthState.NOT_LOGGED_IN: (
                "🔐 *Login dulu yuk*\n\n"
                "Anda perlu login untuk akses email.\n"
                "Format: `/login email@vci.co.id password`\n\n"
                "💡 Kalau pernah login sebelumnya, ketik `/login` saja "
                "(tanpa argumen) untuk quick re-login."
            ),
            AuthState.SESSION_EXPIRED: (
                "⏰ *Session expired*\n\n"
                "Session 8 jam Anda sudah habis.\n"
                "Ketik `/login` saja (tanpa argumen) untuk quick re-login "
                "menggunakan credential tersimpan."
            ),
            AuthState.NO_CREDENTIAL: (
                "⚠️ *Credential tidak ditemukan*\n\n"
                "Silakan login ulang: `/login email@vci.co.id password`"
            ),
        }
        return messages.get(self.state, "")


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

async def check_auth(jid: str, require_credential: bool = True) -> AuthResult:
    """
    Full auth check untuk satu JID.

    Args:
        jid: WhatsApp JID
        require_credential: True kalau handler butuh credential
                           (e.g. /email today butuh, /help tidak)

    Returns:
        AuthResult dengan state + (optionally) session & credential
    """
    # ── Step 1: Whitelist check ───────────────────────────────
    is_authorized = await whitelist.is_authorized(jid)
    if not is_authorized:
        # Admin selalu authorized (bypass whitelist)
        if not whitelist.is_admin(jid):
            return AuthResult(state=AuthState.NOT_WHITELISTED)

    # ── Step 2: Session check ─────────────────────────────────
    # Note: Admin juga butuh session untuk akses email
    # (kecuali untuk /admin commands yang tidak butuh credential)
    if not require_credential:
        return AuthResult(state=AuthState.AUTHORIZED)

    session = await session_manager.get(jid)
    if session is None:
        # Cek apakah credential masih ada (untuk hint quick re-login)
        cred_exists = await credential_store.exists(jid)
        if cred_exists:
            return AuthResult(state=AuthState.SESSION_EXPIRED)
        return AuthResult(state=AuthState.NOT_LOGGED_IN)

    # ── Step 3: Fetch credential ──────────────────────────────
    credential = await credential_store.get(jid)
    if credential is None:
        # Edge case: session ada tapi credential tidak (data inconsistency)
        logger.warning(
            f"[AuthMiddleware] Session exists but no credential for {jid}. "
            "Cleaning up orphan session."
        )
        await session_manager.delete(jid)
        return AuthResult(state=AuthState.NO_CREDENTIAL)

    return AuthResult(
        state=AuthState.AUTHORIZED,
        session=session,
        credential=credential,
    )


async def check_admin(jid: str) -> bool:
    """Quick check: apakah JID adalah admin."""
    return whitelist.is_admin(jid)


async def cleanup_user(jid: str) -> dict:
    """
    Cleanup semua data user (dipakai saat /admin remove atau /logout).

    Returns:
        Dict dengan info apa saja yang dihapus
    """
    result = {
        "session": False,
        "credential": False,
        "whitelist": False,
        "notify_optin": False,
    }

    # Hapus session
    result["session"] = await session_manager.delete(jid)

    # Hapus credential
    result["credential"] = await credential_store.delete(jid)

    # Hapus dari whitelist (kalau ada)
    result["whitelist"] = await whitelist.remove(jid)

    # TODO: Hapus dari notify opt-in (akan ada di Sub-Tahap 2B)
    # result["notify_optin"] = await notify_manager.disable(jid)

    logger.info(f"[AuthMiddleware] Cleanup user {jid}: {result}")
    return result