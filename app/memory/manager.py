import json
import time
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class MemoryManager:
    """
    Kelola riwayat percakapan per JID via Redis.

    Storage:
    - history:{jid}    → List<JSON> (message log, user/assistant only)
    - meta:{jid}       → JSON (push name, type, last_seen)
    - ratelimit:{jid}  → Counter dengan window TTL
    """

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(f"[Memory] Redis connected → {settings.redis_url}")
        return self._redis

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            logger.info("[Memory] Redis connection closed.")

    # ── Key builders ──────────────────────────────────────────

    @staticmethod
    def _history_key(jid: str) -> str:
        return f"history:{jid}"

    @staticmethod
    def _meta_key(jid: str) -> str:
        return f"meta:{jid}"

    @staticmethod
    def _ratelimit_key(jid: str) -> str:
        return f"ratelimit:{jid}"

    # ── History ───────────────────────────────────────────────

    async def add_message(self, jid: str, role: str, content: str) -> None:
        try:
            r = await self._get_redis()
            key = self._history_key(jid)

            payload = {
                "role": role,
                "content": content,
                "timestamp": int(time.time()),
            }

            pipe = r.pipeline()
            pipe.rpush(key, json.dumps(payload, ensure_ascii=False))
            pipe.ltrim(key, -settings.max_history_messages, -1)
            pipe.expire(key, settings.history_ttl_seconds)
            await pipe.execute()

            logger.debug(f"[Memory] +{role} for {jid}")
        except Exception as e:
            logger.error(f"[Memory] add_message error | {jid} | {e}")

    async def get_history(self, jid: str) -> list[dict]:
        """
        Return history TANPA system prompt.
        System prompt akan di-inject oleh router dengan context yang tepat.

        Format: [{"role": "user", ...}, {"role": "assistant", ...}, ...]
        """
        base: list[dict] = []
        try:
            r = await self._get_redis()
            raw_messages = await r.lrange(self._history_key(jid), 0, -1)

            for raw in raw_messages:
                try:
                    msg = json.loads(raw)
                    base.append({"role": msg["role"], "content": msg["content"]})
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"[Memory] corrupt msg in {jid}: {e}")
                    continue

            logger.debug(f"[Memory] loaded {len(base)} msgs for {jid}")
            return base

        except Exception as e:
            logger.error(f"[Memory] get_history error | {jid} | {e}")
            return base

    async def clear_history(self, jid: str) -> bool:
        try:
            r = await self._get_redis()
            await r.delete(self._history_key(jid), self._meta_key(jid))
            logger.info(f"[Memory] cleared history for {jid}")
            return True
        except Exception as e:
            logger.error(f"[Memory] clear_history error | {jid} | {e}")
            return False

    # ── Meta ──────────────────────────────────────────────────

    async def save_meta(
        self,
        jid: str,
        push_name: str,
        is_group: bool,
    ) -> None:
        """
        push_name: PushName dari WhatsApp (private) atau group subject.
        """
        try:
            r = await self._get_redis()
            meta = {
                "push_name": push_name,
                "is_group": is_group,
                "last_seen": int(time.time()),
            }
            await r.set(
                self._meta_key(jid),
                json.dumps(meta, ensure_ascii=False),
                ex=settings.history_ttl_seconds,
            )
        except Exception as e:
            logger.error(f"[Memory] save_meta error | {jid} | {e}")

    async def get_meta(self, jid: str) -> Optional[dict]:
        try:
            r = await self._get_redis()
            raw = await r.get(self._meta_key(jid))
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"[Memory] get_meta error | {jid} | {e}")
            return None

    # ── Stats per JID ─────────────────────────────────────────

    async def get_stats(self, jid: str) -> dict:
        try:
            r = await self._get_redis()
            key = self._history_key(jid)
            count = await r.llen(key)
            ttl = await r.ttl(key)

            return {
                "jid": jid,
                "message_count": count,
                "max_history": settings.max_history_messages,
                "ttl_seconds": ttl,
                "ttl_hours": round(ttl / 3600, 1) if ttl > 0 else 0,
            }
        except Exception as e:
            logger.error(f"[Memory] get_stats error | {jid} | {e}")
            return {}

    # ── Health ────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            r = await self._get_redis()
            return await r.ping() is True
        except Exception:
            return False

    # ── Rate limiter ──────────────────────────────────────────

    async def is_rate_limited(
        self,
        jid: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """
        Fixed-window counter. Return True kalau melebihi limit.
        """
        limit = limit or settings.rate_limit_max
        window_seconds = window_seconds or settings.rate_limit_window_seconds

        try:
            r = await self._get_redis()
            key = self._ratelimit_key(jid)

            current = await r.incr(key)
            if current == 1:
                await r.expire(key, window_seconds)

            return current > limit

        except Exception as e:
            logger.error(f"[RateLimit] error | {jid} | {e}")
            return False  # Fail-open: kalau Redis mati, jangan blok user


memory_manager = MemoryManager()