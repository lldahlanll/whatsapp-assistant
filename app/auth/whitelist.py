# app/auth/whitelist.py
"""
Whitelist authorization untuk multi-user bot.

Konsep:
- ADMIN_JIDS dari .env (hardcoded, tidak bisa diubah saat runtime)
- WHITELIST: dynamic, admin tambah/hapus user via command
- Storage: Redis Set untuk fast lookup

User flow:
- Admin: selalu bisa pakai bot (bypass whitelist check)
- Whitelisted user: bisa /login dan pakai email commands
- Non-whitelisted: di-reject + admin di-notify
"""
import json
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


@dataclass
class WhitelistedUser:
    jid: str
    display_name: str   # nama untuk admin tampilkan, e.g. "Budi"
    added_at: int       # timestamp Unix
    added_by: str       # JID admin yang nambahin


class Whitelist:
    """
    Whitelist authorization.

    Storage:
      whitelist:users     → Hash {jid: JSON{display_name, added_at, added_by}}
      whitelist:admin_set → Set of admin JIDs (loaded from env, but cached for speed)
    """

    USERS_KEY = "whitelist:users"

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        # Admin JIDs: parse sekali saat init, tidak berubah saat runtime
        self._admin_jids: set[str] = self._parse_admin_jids()

    def _parse_admin_jids(self) -> set[str]:
        """Parse ADMIN_JIDS dari .env (comma-separated)."""
        raw = settings.admin_jids or ""
        jids = {j.strip() for j in raw.split(",") if j.strip()}
        if not jids:
            logger.warning(
                "[Whitelist] ⚠️ ADMIN_JIDS belum diset di .env! "
                "Tidak ada admin yang bisa manage whitelist."
            )
        else:
            logger.info(f"[Whitelist] ✓ Loaded {len(jids)} admin(s)")
        return jids

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

    # ── Public API ────────────────────────────────────────────

    def is_admin(self, jid: str) -> bool:
        """Cek apakah JID adalah admin (sync — pakai cache lokal)."""
        return jid in self._admin_jids

    async def is_authorized(self, jid: str) -> bool:
        """
        Cek apakah JID boleh pakai bot.
        Admin OR whitelisted user.
        """
        if self.is_admin(jid):
            return True

        try:
            r = await self._get_redis()
            return await r.hexists(self.USERS_KEY, jid)
        except Exception as e:
            logger.error(f"[Whitelist] is_authorized check failed: {e}")
            return False

    async def add(
        self,
        jid: str,
        display_name: str,
        added_by: str,
    ) -> bool:
        """Tambah user ke whitelist."""
        try:
            import time
            r = await self._get_redis()
            payload = json.dumps({
                "display_name": display_name,
                "added_at": int(time.time()),
                "added_by": added_by,
            })
            added = await r.hset(self.USERS_KEY, jid, payload)
            logger.info(
                f"[Whitelist] ✓ Added {jid} ({display_name}) "
                f"by admin {added_by}"
            )
            return bool(added)
        except Exception as e:
            logger.error(f"[Whitelist] add failed: {e}")
            return False

    async def remove(self, jid: str) -> bool:
        """Hapus user dari whitelist."""
        try:
            r = await self._get_redis()
            removed = await r.hdel(self.USERS_KEY, jid)
            if removed:
                logger.info(f"[Whitelist] ✓ Removed {jid}")
            return bool(removed)
        except Exception as e:
            logger.error(f"[Whitelist] remove failed: {e}")
            return False

    async def list_users(self) -> list[WhitelistedUser]:
        """List semua user di whitelist."""
        try:
            r = await self._get_redis()
            data = await r.hgetall(self.USERS_KEY)

            users = []
            for jid, payload in data.items():
                try:
                    info = json.loads(payload)
                    users.append(WhitelistedUser(
                        jid=jid,
                        display_name=info.get("display_name", "Unknown"),
                        added_at=info.get("added_at", 0),
                        added_by=info.get("added_by", "unknown"),
                    ))
                except json.JSONDecodeError:
                    continue

            # Sort by added_at descending (newest first)
            users.sort(key=lambda u: u.added_at, reverse=True)
            return users

        except Exception as e:
            logger.error(f"[Whitelist] list_users failed: {e}")
            return []

    def get_admin_jids(self) -> set[str]:
        """Untuk notif ke admin saat ada user baru request akses."""
        return self._admin_jids.copy()


# Singleton
whitelist = Whitelist()