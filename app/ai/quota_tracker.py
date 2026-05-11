# app/ai/quota_tracker.py
"""
Quota tracker per-endpoint per-model dengan reset window otomatis.

Tujuan: SKIP request sebelum dikirim kalau quota habis.
Hemat: latency (no wasted timeout), token (no wasted retry), API rate limit.

Strategi:
- Free-tier limits di-encode sebagai konfigurasi (QUOTA_LIMITS)
- Counter di Redis dengan TTL = window reset
- Bucketing: per-minute untuk RPM, per-day (UTC) untuk RPD
- Atomic INCR + EXPIRE via pipeline (race-safe)
- Fail-open kalau Redis down (bot tetap jalan, tracking lost)

Pattern usage:
    if not await quota_tracker.has_budget(endpoint, model):
        continue  # skip route ini, lanjut fallback
    # ... call API ...
    await quota_tracker.record_call(endpoint, model)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


@dataclass(frozen=True)
class QuotaLimit:
    """Konfigurasi quota untuk satu kombinasi endpoint+model."""

    rpm: Optional[int] = None  # requests per minute
    rpd: Optional[int] = None  # requests per day (UTC)


# ─────────────────────────────────────────────────────────────
# Known free-tier limits
# ─────────────────────────────────────────────────────────────
# Format key: "{endpoint_name}:{model_id}"
# Note: Limits berdasarkan public docs. Verify periodik di:
#   - Groq:       https://console.groq.com/docs/rate-limits
#   - Gemini:     https://ai.google.dev/pricing
#   - OpenRouter: https://openrouter.ai/docs/limits
#
# Strategy: kita SET counter SLIGHTLY BELOW actual limit (95%)
# untuk safety margin terhadap clock drift & racing.
QUOTA_LIMITS: dict[str, QuotaLimit] = {
    # ── Groq (per-minute rate limit) ──────────────────────────
    "groq-main:llama-3.1-8b-instant": QuotaLimit(rpm=30, rpd=14400),
    "groq-main:llama-3.3-70b-versatile": QuotaLimit(rpm=30, rpd=1000),
    "groq-main:meta-llama/llama-4-scout-17b-16e-instruct": QuotaLimit(rpm=30, rpd=1000),
    "groq-main:qwen/qwen3-32b": QuotaLimit(rpm=60, rpd=1000),
    "groq-main:openai/gpt-oss-120b": QuotaLimit(rpm=30, rpd=1000),
    # ── Gemini (per-day, reset midnight UTC) ──────────────────
    "gemini-acc1:gemini-2.5-flash-lite": QuotaLimit(rpm=15, rpd=1000),
    "gemini-acc2:gemini-2.5-flash-lite": QuotaLimit(rpm=15, rpd=1000),
    "gemini-acc1:gemini-2.5-flash": QuotaLimit(rpm=10, rpd=250),
    "gemini-acc2:gemini-2.5-flash": QuotaLimit(rpm=10, rpd=250),
    "gemini-acc1:gemini-2.5-pro": QuotaLimit(rpm=5, rpd=25),  # tight!
    "gemini-acc2:gemini-2.5-pro": QuotaLimit(rpm=5, rpd=25),
    # ── OpenRouter (per-day :free tier) ───────────────────────
    # OpenRouter free: 50 req/hari kalau saldo < $10, 1000 kalau ≥ $10
    "openrouter-acc1:qwen/qwen3-coder:free": QuotaLimit(rpd=50),
    "openrouter-acc2:qwen/qwen3-coder:free": QuotaLimit(rpd=50),
    "openrouter-acc1:openai/gpt-oss-120b:free": QuotaLimit(rpd=50),
    "openrouter-acc2:openai/gpt-oss-120b:free": QuotaLimit(rpd=50),
    "openrouter-acc1:nvidia/nemotron-3-super-120b-a12b:free": QuotaLimit(rpd=50),
    "openrouter-acc2:nvidia/nemotron-3-super-120b-a12b:free": QuotaLimit(rpd=50),
    "openrouter-acc1:google/gemma-4-26b-a4b-it:free": QuotaLimit(rpd=50),
}


def _seconds_until_midnight_utc() -> int:
    """Hitung detik sampai tengah malam UTC (Gemini reset window)."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(int((midnight - now).total_seconds()), 60)


class QuotaTracker:
    """
    Pre-flight quota check + post-call accounting via Redis.
    Singleton-friendly: stateless apart from Redis connection.
    """

    _SAFETY_MARGIN = 0.95  # pakai max 95% dari real quota

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── Key Builders ──────────────────────────────────────────

    @staticmethod
    def _key_rpm(endpoint: str, model: str) -> str:
        # Bucket per-minute via floor division on epoch seconds
        bucket = int(datetime.now(timezone.utc).timestamp() // 60)
        return f"quota:rpm:{endpoint}:{model}:{bucket}"

    @staticmethod
    def _key_rpd(endpoint: str, model: str) -> str:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"quota:rpd:{endpoint}:{model}:{date}"

    # ── Public API ────────────────────────────────────────────

    async def has_budget(self, endpoint: str, model: str) -> bool:
        """
        Cek apakah masih ada budget request.

        Returns:
            True  → safe to proceed (budget tersedia atau model unknown)
            False → quota exhausted, router should skip this route
        """
        key = f"{endpoint}:{model}"
        limit = QUOTA_LIMITS.get(key)
        if limit is None:
            return True  # Unknown model → assume aman, jangan blok

        try:
            r = await self._get_redis()

            if limit.rpm is not None:
                effective = max(int(limit.rpm * self._SAFETY_MARGIN), 1)
                count = int(await r.get(self._key_rpm(endpoint, model)) or 0)
                if count >= effective:
                    logger.warning(
                        f"[Quota] ⛔ {key} RPM exhausted: {count}/{effective}"
                    )
                    return False

            if limit.rpd is not None:
                effective = max(int(limit.rpd * self._SAFETY_MARGIN), 1)
                count = int(await r.get(self._key_rpd(endpoint, model)) or 0)
                if count >= effective:
                    logger.warning(
                        f"[Quota] ⛔ {key} RPD exhausted: {count}/{effective}"
                    )
                    return False

            return True
        except Exception as e:
            # Redis down → fail-open agar bot tetap jalan
            logger.error(f"[Quota] check failed for {key}, fail-open: {e}")
            return True

    async def record_call(self, endpoint: str, model: str) -> None:
        """
        Increment counter setelah call (sukses atau gagal).
        Dipanggil unconditionally setelah setiap API hit.
        """
        key = f"{endpoint}:{model}"
        limit = QUOTA_LIMITS.get(key)
        if limit is None:
            return

        try:
            r = await self._get_redis()
            pipe = r.pipeline()

            if limit.rpm is not None:
                k = self._key_rpm(endpoint, model)
                pipe.incr(k)
                pipe.expire(k, 70)  # TTL > 60s biar aman dari jitter

            if limit.rpd is not None:
                k = self._key_rpd(endpoint, model)
                pipe.incr(k)
                pipe.expire(k, _seconds_until_midnight_utc())

            await pipe.execute()
        except Exception as e:
            logger.error(f"[Quota] record_call failed for {key}: {e}")

    async def snapshot(self) -> dict[str, dict]:
        """
        Snapshot current usage untuk health/monitoring endpoint.
        Returns dict keyed by "endpoint:model".
        """
        try:
            r = await self._get_redis()
            result: dict[str, dict] = {}

            # Batch GET via pipeline untuk efficiency
            pipe = r.pipeline()
            keys_to_fetch: list[tuple[str, str, str]] = (
                []
            )  # (composite_key, kind, redis_key)

            for key, limit in QUOTA_LIMITS.items():
                endpoint, model = key.split(":", 1)
                if limit.rpm is not None:
                    rk = self._key_rpm(endpoint, model)
                    pipe.get(rk)
                    keys_to_fetch.append((key, "rpm", rk))
                if limit.rpd is not None:
                    rk = self._key_rpd(endpoint, model)
                    pipe.get(rk)
                    keys_to_fetch.append((key, "rpd", rk))

            values = await pipe.execute()

            # Aggregate per composite key
            for (composite_key, kind, _), value in zip(keys_to_fetch, values):
                limit = QUOTA_LIMITS[composite_key]
                entry = result.setdefault(
                    composite_key,
                    {
                        "rpm_used": None,
                        "rpm_limit": limit.rpm,
                        "rpd_used": None,
                        "rpd_limit": limit.rpd,
                    },
                )
                used = int(value or 0)
                entry[f"{kind}_used"] = used

            return result
        except Exception as e:
            logger.error(f"[Quota] snapshot failed: {e}")
            return {}

    async def reset(self, endpoint: str, model: str) -> None:
        """Manual reset — for testing/admin override."""
        try:
            r = await self._get_redis()
            await r.delete(
                self._key_rpm(endpoint, model),
                self._key_rpd(endpoint, model),
            )
            logger.info(f"[Quota] ✓ Reset {endpoint}:{model}")
        except Exception as e:
            logger.error(f"[Quota] reset failed: {e}")


# Singleton instance
quota_tracker = QuotaTracker()
