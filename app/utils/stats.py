import json
import time
import os
from loguru import logger
from typing import Optional

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

class StatsTracker:
    """
    Track usage statistik bot — disimpan di Redis.
    
    Metrics yang ditrack:
    - Total pesan masuk
    - Total response berhasil / gagal
    - Usage per model (berapa kali dipanggil)
    - Average response time per model
    - Active users (unique JID)
    """

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    # ── Key builders ──────────────────────────────────────────

    def _today(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    def _key(self, metric: str) -> str:
        return f"stats:{self._today()}:{metric}"

    # ── Track metrics ─────────────────────────────────────────

    async def track_message_received(self, jid: str, is_group: bool):
        """Catat pesan masuk."""
        try:
            r = await self._get_redis()
            pipe = r.pipeline()
            pipe.incr(self._key("messages_received"))
            pipe.incr(self._key("groups" if is_group else "private"))
            pipe.sadd(self._key("active_users"), jid)   # unique users
            pipe.expire(self._key("messages_received"), 7 * 86400)
            pipe.expire(self._key("active_users"), 7 * 86400)
            await pipe.execute()
        except Exception as e:
            logger.error(f"[Stats] track_message_received error: {e}")

    async def track_response(
        self,
        model_name: str,
        success: bool,
        response_time_ms: float,
    ):
        """Catat response dari AI model."""
        try:
            r = await self._get_redis()
            pipe = r.pipeline()

            if success:
                pipe.incr(self._key("responses_success"))
                pipe.incr(self._key(f"model:{model_name}"))
                # Simpan response time untuk rata-rata
                pipe.lpush(self._key(f"rt:{model_name}"), response_time_ms)
                pipe.ltrim(self._key(f"rt:{model_name}"), 0, 99)  # max 100 data
            else:
                pipe.incr(self._key("responses_failed"))

            pipe.expire(self._key("responses_success"), 7 * 86400)
            pipe.expire(self._key("responses_failed"), 7 * 86400)
            await pipe.execute()
        except Exception as e:
            logger.error(f"[Stats] track_response error: {e}")

    async def track_command(self, command: str):
        """Catat penggunaan command."""
        try:
            r = await self._get_redis()
            await r.incr(self._key(f"cmd:{command}"))
        except Exception as e:
            logger.error(f"[Stats] track_command error: {e}")

    # ── Get summary ───────────────────────────────────────────

    async def get_daily_summary(self, date: Optional[str] = None) -> dict:
        """Ambil ringkasan statistik harian."""
        try:
            r = await self._get_redis()
            d = date or self._today()
            prefix = f"stats:{d}"

            # Ambil semua metrics
            received  = await r.get(f"{prefix}:messages_received") or "0"
            success   = await r.get(f"{prefix}:responses_success") or "0"
            failed    = await r.get(f"{prefix}:responses_failed") or "0"
            private   = await r.get(f"{prefix}:private") or "0"
            groups    = await r.get(f"{prefix}:groups") or "0"
            users     = await r.scard(f"{prefix}:active_users") or 0

            # Model usage
            from app.ai.models import MODELS, ModelTier
            model_usage = {}
            for tier, model in MODELS.items():
                count = await r.get(f"{prefix}:model:{model.name}") or "0"
                
                # Average response time
                rt_list = await r.lrange(f"{prefix}:rt:{model.name}", 0, -1)
                if rt_list:
                    avg_rt = sum(float(x) for x in rt_list) / len(rt_list)
                else:
                    avg_rt = 0

                model_usage[model.name] = {
                    "count": int(count),
                    "avg_response_time_ms": round(avg_rt, 1),
                }

            return {
                "date": d,
                "messages_received": int(received),
                "responses_success": int(success),
                "responses_failed": int(failed),
                "private_messages": int(private),
                "group_messages": int(groups),
                "active_users": int(users),
                "success_rate": (
                    round(int(success) / max(int(received), 1) * 100, 1)
                ),
                "model_usage": model_usage,
            }
        except Exception as e:
            logger.error(f"[Stats] get_daily_summary error: {e}")
            return {}

    async def close(self):
        if self._redis:
            await self._redis.aclose()


# Singleton
stats_tracker = StatsTracker()