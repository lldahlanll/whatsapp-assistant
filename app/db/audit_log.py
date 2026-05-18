# app/db/audit_log.py
"""
Audit log untuk customer lookup.

Design: Redis Stream dengan TTL pendek (7 hari).
Tujuan: forensic kalau ada keluhan ("kok nomor saya muncul?"),
bukan archival jangka panjang.
"""
import json
import time
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class LookupAuditLog:
    """Append-only audit log untuk customer lookups."""

    STREAM_KEY = "audit:customer_lookup"
    MAX_LEN = 10_000  # cap stream length
    TTL_SECONDS = 7 * 24 * 60 * 60  # 7 hari

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def log(
        self,
        *,
        requester_jid: str,
        requester_name: str,
        group_jid: str,
        phone_searched: str,
        result_count: int,
        elapsed_ms: float,
    ) -> None:
        """
        Append entry. Non-blocking — failure jangan ganggu main flow.
        Tidak menyimpan Kode_kustomer hasil (sesuai permintaan: data sementara).
        """
        entry = {
            "ts": int(time.time()),
            "requester": requester_jid,
            "name": requester_name,
            "group": group_jid,
            "phone": phone_searched,
            "hits": result_count,
            "ms": int(elapsed_ms),
        }
        try:
            r = await self._get_redis()
            await r.xadd(
                self.STREAM_KEY,
                {"data": json.dumps(entry, ensure_ascii=False)},
                maxlen=self.MAX_LEN,
                approximate=True,
            )
            # Refresh TTL pada stream key (sliding window)
            await r.expire(self.STREAM_KEY, self.TTL_SECONDS)
        except Exception as e:
            # Jangan raise — audit failure tidak boleh blok user flow
            logger.error(f"[AuditLog] Failed to log: {e}")


audit_log = LookupAuditLog()