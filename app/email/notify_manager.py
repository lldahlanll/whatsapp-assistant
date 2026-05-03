# app/email/notify_manager.py
"""
Per-user email notification opt-in manager.

Simpan di Redis dengan key: email:notify:{jid}
Value: "1" (opted in)

Dipakai oleh:
- MultiUserEmailScheduler → ambil daftar opted-in users
- /email notify on/off    → toggle
- cleanup_user            → hapus saat user removed
"""
import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class NotifyOptInManager:
    KEY_PREFIX = "email:notify:"
    SCAN_PATTERN = "email:notify:*"
    TTL = 86400 * 90  # 90 hari — refresh tiap toggle on

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

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
            self._redis = None

    def _key(self, jid: str) -> str:
        return f"{self.KEY_PREFIX}{jid}"

    async def enable(self, jid: str) -> None:
        r = await self._get_redis()
        await r.set(self._key(jid), "1", ex=self.TTL)
        logger.info(f"[NotifyOptIn] {jid} → enabled")

    async def disable(self, jid: str) -> bool:
        r = await self._get_redis()
        deleted = await r.delete(self._key(jid))
        logger.info(f"[NotifyOptIn] {jid} → disabled (deleted={deleted})")
        return bool(deleted)

    async def is_enabled(self, jid: str) -> bool:
        r = await self._get_redis()
        return bool(await r.exists(self._key(jid)))

    async def get_all_opted_in(self) -> list[str]:
        """Return semua JID yang opted-in. Dipakai scheduler."""
        r = await self._get_redis()
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await r.scan(
                cursor=cursor, match=self.SCAN_PATTERN, count=100
            )
            keys.extend(batch)
            if cursor == 0:
                break
        # Strip prefix → JID
        prefix_len = len(self.KEY_PREFIX)
        return [k[prefix_len:] for k in keys]


notify_opt_in_manager = NotifyOptInManager()