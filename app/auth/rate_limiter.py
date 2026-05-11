# app/auth/rate_limiter.py
"""
Rate limiter untuk anonymous (non-whitelisted) users.

Tujuan: cegah abuse chat AI yang public, tapi tetap responsif.
- Whitelisted/admin: unlimited
- Anonymous: N pesan per window (sliding window via Redis)
"""
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class RateLimiter:
    """Sliding window rate limiter berbasis Redis sorted set."""

    KEY_PREFIX = "ratelimit:ai:"

    def __init__(
        self,
        max_requests: int = 20,
        window_seconds: int = 3600,  # 20 msg/hour untuk anonymous
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def check_and_consume(self, jid: str) -> tuple[bool, int]:
        """
        Return (allowed, remaining).
        Atomic via Redis pipeline — race-safe.
        """
        import time
        now = int(time.time() * 1000)
        cutoff = now - (self.window_seconds * 1000)
        key = f"{self.KEY_PREFIX}{jid}"

        try:
            r = await self._get_redis()
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)        # bersihkan entry lama
            pipe.zcard(key)                              # count current window
            pipe.zadd(key, {str(now): now})              # tambah entry baru
            pipe.expire(key, self.window_seconds + 60)   # auto-cleanup
            _, current_count, _, _ = await pipe.execute()

            allowed = current_count < self.max_requests
            remaining = max(0, self.max_requests - current_count - 1)

            if not allowed:
                # Rollback: jangan hitung request yang ditolak
                await r.zrem(key, str(now))
                logger.warning(
                    f"[RateLimit] Blocked {jid}: "
                    f"{current_count}/{self.max_requests} in window"
                )

            return allowed, remaining

        except Exception as e:
            logger.error(f"[RateLimit] Check failed: {e}, allowing by default")
            return True, self.max_requests  # fail-open


# Singleton untuk anonymous chat AI
ai_rate_limiter = RateLimiter(max_requests=20, window_seconds=3600)