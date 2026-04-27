from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class StatsTracker:
    """Daily metrics tracker via Redis. Semua key punya TTL eksplisit."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._ttl = settings.stats_ttl_seconds

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
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _key(self, metric: str, date: Optional[str] = None) -> str:
        return f"stats:{date or self._today()}:{metric}"

    # ── Track ─────────────────────────────────────────────────

    async def track_message_received(self, jid: str, is_group: bool) -> None:
        try:
            r = await self._get_redis()
            pipe = r.pipeline()

            keys_to_expire = [
                self._key("messages_received"),
                self._key("groups" if is_group else "private"),
                self._key("active_users"),
            ]

            pipe.incr(self._key("messages_received"))
            pipe.incr(self._key("groups" if is_group else "private"))
            pipe.sadd(self._key("active_users"), jid)

            for k in keys_to_expire:
                pipe.expire(k, self._ttl)

            await pipe.execute()
        except Exception as e:
            logger.error(f"[Stats] track_message_received | {e}")

    async def track_response(
        self,
        model_name: str,
        success: bool,
        response_time_ms: float,
    ) -> None:
        try:
            r = await self._get_redis()
            pipe = r.pipeline()

            if success:
                k_model = self._key(f"model:{model_name}")
                k_rt = self._key(f"rt:{model_name}")
                k_ok = self._key("responses_success")

                pipe.incr(k_ok)
                pipe.incr(k_model)
                pipe.lpush(k_rt, response_time_ms)
                pipe.ltrim(k_rt, 0, 99)

                for k in (k_ok, k_model, k_rt):
                    pipe.expire(k, self._ttl)
            else:
                k_fail = self._key("responses_failed")
                pipe.incr(k_fail)
                pipe.expire(k_fail, self._ttl)

            await pipe.execute()
        except Exception as e:
            logger.error(f"[Stats] track_response | {e}")

    async def track_command(self, command: str) -> None:
        try:
            r = await self._get_redis()
            key = self._key(f"cmd:{command}")
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception as e:
            logger.error(f"[Stats] track_command | {e}")

    # ── Read ──────────────────────────────────────────────────

    async def get_daily_summary(self, date: Optional[str] = None) -> dict:
        try:
            r = await self._get_redis()
            d = date or self._today()
            prefix = f"stats:{d}"

            received = int(await r.get(f"{prefix}:messages_received") or 0)
            success = int(await r.get(f"{prefix}:responses_success") or 0)
            failed = int(await r.get(f"{prefix}:responses_failed") or 0)
            private = int(await r.get(f"{prefix}:private") or 0)
            groups = int(await r.get(f"{prefix}:groups") or 0)
            users = int(await r.scard(f"{prefix}:active_users") or 0)

            from app.ai.models import MODELS

            model_usage = {}
            for model in MODELS.values():
                count = int(await r.get(f"{prefix}:model:{model.name}") or 0)
                rt_list = await r.lrange(f"{prefix}:rt:{model.name}", 0, -1)
                avg_rt = (
                    sum(float(x) for x in rt_list) / len(rt_list)
                    if rt_list else 0.0
                )
                model_usage[model.name] = {
                    "count": count,
                    "avg_response_time_ms": round(avg_rt, 1),
                }

            return {
                "date": d,
                "messages_received": received,
                "responses_success": success,
                "responses_failed": failed,
                "private_messages": private,
                "group_messages": groups,
                "active_users": users,
                "success_rate": round(success / max(received, 1) * 100, 1),
                "model_usage": model_usage,
            }
        except Exception as e:
            logger.error(f"[Stats] get_daily_summary | {e}")
            return {}


stats_tracker = StatsTracker()