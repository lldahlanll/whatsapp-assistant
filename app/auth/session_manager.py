# app/auth/session_manager.py
"""
Session lifecycle untuk multi-user auth.

Konsep:
- User /login → buat session dengan TTL 8 jam
- Setiap activity, session BISA di-extend (sliding window) atau tidak
- Setelah TTL habis, session expired → user harus login ulang
- /logout → delete session immediately

Storage Redis:
  session:{jid} → JSON {created_at, expires_at, email}
"""
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


@dataclass
class Session:
    jid: str
    email: str             # email user yang login (untuk display)
    created_at: int        # timestamp Unix
    expires_at: int        # timestamp Unix

    @property
    def is_active(self) -> bool:
        return time.time() < self.expires_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at - time.time()))

    @property
    def remaining_human(self) -> str:
        secs = self.remaining_seconds
        if secs >= 3600:
            return f"{secs // 3600}h {(secs % 3600) // 60}m"
        if secs >= 60:
            return f"{secs // 60}m"
        return f"{secs}s"


class SessionManager:
    """
    Manage user sessions di Redis.

    Default TTL: 8 jam (work day).
    Session TIDAK auto-extend — user re-login kalau expired.
    """

    KEY_PREFIX = "session:"
    DEFAULT_TTL = 8 * 60 * 60  # 8 jam

    def __init__(self, ttl_seconds: int = DEFAULT_TTL) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._ttl = ttl_seconds

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    @staticmethod
    def _key(jid: str) -> str:
        return f"{SessionManager.KEY_PREFIX}{jid}"

    # ── Public API ────────────────────────────────────────────

    async def create(self, jid: str, email: str) -> Session:
        """Buat session baru (overwrite kalau sudah ada)."""
        now = int(time.time())
        session = Session(
            jid=jid,
            email=email,
            created_at=now,
            expires_at=now + self._ttl,
        )

        try:
            r = await self._get_redis()
            payload = json.dumps({
                "email": email,
                "created_at": now,
                "expires_at": session.expires_at,
            })
            await r.set(self._key(jid), payload, ex=self._ttl)
            logger.info(
                f"[SessionManager] ✓ Created session for {jid} "
                f"(email: {email}, expires in {self._ttl // 3600}h)"
            )
        except Exception as e:
            logger.error(f"[SessionManager] create failed for {jid}: {e}")

        return session

    async def get(self, jid: str) -> Optional[Session]:
        """Get session untuk JID. Return None kalau tidak ada/expired."""
        try:
            r = await self._get_redis()
            raw = await r.get(self._key(jid))
            if not raw:
                return None

            data = json.loads(raw)
            session = Session(
                jid=jid,
                email=data["email"],
                created_at=data["created_at"],
                expires_at=data["expires_at"],
            )

            # Double check expiry (Redis TTL biasanya akurat tapi safety)
            if not session.is_active:
                await self.delete(jid)
                return None

            return session

        except Exception as e:
            logger.error(f"[SessionManager] get failed for {jid}: {e}")
            return None

    async def is_active(self, jid: str) -> bool:
        """Quick check tanpa fetch full session data."""
        session = await self.get(jid)
        return session is not None and session.is_active

    async def delete(self, jid: str) -> bool:
        """Logout — hapus session."""
        try:
            r = await self._get_redis()
            deleted = await r.delete(self._key(jid))
            if deleted:
                logger.info(f"[SessionManager] ✓ Deleted session for {jid}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"[SessionManager] delete failed for {jid}: {e}")
            return False

    async def list_active(self) -> list[Session]:
        """List semua active session (untuk admin command)."""
        try:
            r = await self._get_redis()
            keys = await r.keys(f"{self.KEY_PREFIX}*")

            sessions = []
            for key in keys:
                raw = await r.get(key)
                if raw:
                    try:
                        data = json.loads(raw)
                        jid = key.replace(self.KEY_PREFIX, "")
                        sessions.append(Session(
                            jid=jid,
                            email=data["email"],
                            created_at=data["created_at"],
                            expires_at=data["expires_at"],
                        ))
                    except Exception:
                        continue

            return [s for s in sessions if s.is_active]

        except Exception as e:
            logger.error(f"[SessionManager] list_active failed: {e}")
            return []


# Singleton
session_manager = SessionManager()