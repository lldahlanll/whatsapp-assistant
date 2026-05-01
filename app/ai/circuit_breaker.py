# app/ai/circuit_breaker.py
"""
Circuit Breaker dengan variable-duration trip.

Improvement dari versi sebelumnya:
- trip_with_duration(): durasi trip bisa di-set per-error type
  → AUTH 401   : 3600s
  → QUOTA 429  : sampai tengah malam (Gemini reset harian)
  → MODEL 404  : 3600s
- status() sekarang tampilkan reason + waktu tersisa
- reset() bisa reset semua atau spesifik key
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class BreakerEntry:
    tripped_at: float
    duration: int      # detik
    reason: str


class CircuitBreaker:
    """
    Track model yang gagal dan disable sementara.

    Key format: "{endpoint_name}:{model_id}"
    Contoh    : "gemini-acc1:gemini-2.5-pro"
    """

    def __init__(self, disable_duration: int = 3600):
        # Default duration untuk trip() backward-compat
        self._default_duration = disable_duration
        self._disabled: dict[str, BreakerEntry] = {}
        self._lock = asyncio.Lock()

    # ── Core API ──────────────────────────────────────────────

    async def is_open(self, model_id: str) -> bool:
        """True kalau model sedang di-disable."""
        async with self._lock:
            entry = self._disabled.get(model_id)
            if entry is None:
                return False

            elapsed = time.time() - entry.tripped_at
            if elapsed >= entry.duration:
                del self._disabled[model_id]
                logger.info(
                    f"[CircuitBreaker] 🔄 {model_id} dibebaskan "
                    f"(was: {entry.reason})"
                )
                return False

            remaining = entry.duration - elapsed
            logger.debug(
                f"[CircuitBreaker] ⛔ {model_id} masih disabled "
                f"({remaining:.0f}s tersisa | reason: {entry.reason})"
            )
            return True

    async def trip(self, model_id: str, reason: str = "") -> None:
        """Trip dengan default duration (backward compat)."""
        await self.trip_with_duration(model_id, reason, self._default_duration)

    async def trip_with_duration(
        self,
        model_id: str,
        reason: str,
        duration: int,
    ) -> None:
        """
        Trip breaker dengan durasi custom.

        Args:
            model_id : Key format "endpoint:model"
            reason   : Deskripsi penyebab (untuk logging)
            duration : Durasi disable dalam detik
        """
        async with self._lock:
            # Jangan re-trip kalau sudah di-disable dengan durasi lebih panjang
            existing = self._disabled.get(model_id)
            if existing:
                remaining = existing.duration - (time.time() - existing.tripped_at)
                if remaining > duration:
                    logger.debug(
                        f"[CircuitBreaker] Skip re-trip {model_id} "
                        f"(existing {remaining:.0f}s > new {duration}s)"
                    )
                    return

            self._disabled[model_id] = BreakerEntry(
                tripped_at=time.time(),
                duration=duration,
                reason=reason,
            )

            hours = duration / 3600
            logger.warning(
                f"[CircuitBreaker] 🔴 {model_id} disabled {duration}s "
                f"({hours:.1f}h) | Reason: {reason}"
            )

    async def reset(self, model_id: Optional[str] = None) -> None:
        """Reset manual — semua atau spesifik model."""
        async with self._lock:
            if model_id:
                removed = self._disabled.pop(model_id, None)
                if removed:
                    logger.info(f"[CircuitBreaker] ✓ Reset: {model_id}")
            else:
                count = len(self._disabled)
                self._disabled.clear()
                logger.info(f"[CircuitBreaker] ✓ Reset all ({count} entries)")

    async def status(self) -> dict[str, dict]:
        """
        Snapshot semua model yang sedang disabled.
        Format: { model_id: { "remaining_sec", "reason", "duration" } }
        """
        async with self._lock:
            now = time.time()
            result = {}
            for mid, entry in list(self._disabled.items()):
                remaining = entry.duration - (now - entry.tripped_at)
                if remaining <= 0:
                    # Expired — bersihkan sambil jalan
                    del self._disabled[mid]
                    continue
                result[mid] = {
                    "remaining_sec": round(remaining),
                    "remaining_human": _format_duration(remaining),
                    "reason": entry.reason,
                    "duration_total": entry.duration,
                }
            return result

    async def get_disabled_count(self) -> int:
        async with self._lock:
            return len(self._disabled)


def _format_duration(seconds: float) -> str:
    """Format detik ke human-readable. Contoh: '2h 15m' atau '45m 30s'"""
    seconds = int(seconds)
    if seconds >= 3600:
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{h}h {m}m"
    elif seconds >= 60:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    return f"{seconds}s"