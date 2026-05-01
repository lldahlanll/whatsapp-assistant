# app/auth/credential_store.py
"""
Encrypted credential storage untuk multi-user email access.

Security model:
- Master key di environment variable (AUTH_MASTER_KEY)
- Per-credential encryption pakai Fernet (AES-128-CBC + HMAC)
- Storage di Redis dengan TTL (auto-expire)
- Plaintext password TIDAK PERNAH disimpan di disk/log

Generate master key sekali saat setup:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import json
import os
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from app.config import settings


@dataclass
class UserCredential:
    """Credential untuk login Zimbra (atau email server lain)."""
    email: str       # username untuk IMAP/SMTP
    password: str    # plaintext (di-encrypt sebelum disimpan)
    display_name: Optional[str] = None  # "Budi Santoso" untuk email signature


class CredentialStore:
    """
    Encrypted store untuk user credentials di Redis.

    Key format: creds:{jid} → encrypted JSON {email, password, display_name}
    TTL       : 30 hari (auto-cleanup user inactive)
    """

    KEY_PREFIX = "creds:"
    TTL_SECONDS = 30 * 24 * 60 * 60  # 30 hari

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._fernet: Optional[Fernet] = None
        self._init_encryption()

    def _init_encryption(self) -> None:
        """
        Initialize Fernet dengan master key dari env.
        Fail fast kalau key tidak ada — security critical.
        """
        master_key = os.getenv("AUTH_MASTER_KEY", "").strip()

        if not master_key:
            raise RuntimeError(
                "❌ AUTH_MASTER_KEY tidak diset di .env!\n"
                "Generate dengan:\n"
                "  python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"\n"
                "Lalu tambahkan ke .env:\n"
                "  AUTH_MASTER_KEY=<generated_key>"
            )

        try:
            self._fernet = Fernet(master_key.encode())
            logger.info("[CredentialStore] ✓ Encryption initialized")
        except (ValueError, Exception) as e:
            raise RuntimeError(
                f"❌ AUTH_MASTER_KEY tidak valid: {e}\n"
                "Pastikan key adalah Fernet key yang valid (44 char base64)"
            )

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=False,  # binary untuk encrypted data
            )
        return self._redis

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @staticmethod
    def _key(jid: str) -> str:
        return f"{CredentialStore.KEY_PREFIX}{jid}"

    # ── Public API ────────────────────────────────────────────

    async def save(self, jid: str, credential: UserCredential) -> bool:
        """
        Simpan credential terenkripsi untuk JID.
        TTL akan reset tiap save.
        """
        try:
            r = await self._get_redis()

            payload = {
                "email": credential.email,
                "password": credential.password,
                "display_name": credential.display_name or "",
            }

            plaintext = json.dumps(payload).encode("utf-8")
            ciphertext = self._fernet.encrypt(plaintext)

            await r.set(
                self._key(jid),
                ciphertext,
                ex=self.TTL_SECONDS,
            )

            logger.info(
                f"[CredentialStore] ✓ Saved credential for {jid} "
                f"(email: {credential.email})"
            )
            return True

        except Exception as e:
            logger.error(f"[CredentialStore] save failed for {jid}: {e}")
            return False

    async def get(self, jid: str) -> Optional[UserCredential]:
        """
        Ambil dan decrypt credential. Return None kalau tidak ada/error.
        """
        try:
            r = await self._get_redis()
            ciphertext = await r.get(self._key(jid))

            if not ciphertext:
                return None

            plaintext = self._fernet.decrypt(ciphertext)
            data = json.loads(plaintext.decode("utf-8"))

            return UserCredential(
                email=data["email"],
                password=data["password"],
                display_name=data.get("display_name") or None,
            )

        except InvalidToken:
            # Encryption key changed → credential tidak bisa di-decrypt
            logger.error(
                f"[CredentialStore] InvalidToken for {jid} — "
                "AUTH_MASTER_KEY mungkin berubah! User harus re-login."
            )
            # Cleanup invalid entry
            await self.delete(jid)
            return None

        except Exception as e:
            logger.error(f"[CredentialStore] get failed for {jid}: {e}")
            return None

    async def delete(self, jid: str) -> bool:
        """Hapus credential (logout permanent)."""
        try:
            r = await self._get_redis()
            deleted = await r.delete(self._key(jid))
            if deleted:
                logger.info(f"[CredentialStore] ✓ Deleted credential for {jid}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"[CredentialStore] delete failed for {jid}: {e}")
            return False

    async def exists(self, jid: str) -> bool:
        """Cek apakah JID punya credential tersimpan."""
        try:
            r = await self._get_redis()
            return await r.exists(self._key(jid)) > 0
        except Exception:
            return False


# Singleton — initialized saat first import
credential_store = CredentialStore()