import asyncio
import time
from loguru import logger


class CircuitBreaker:
    """
    Track model yang gagal dan disable sementara.

    Pattern: ketika model return 401/403/404, anggap "rusak"
    dan skip selama disable_duration. Setelah waktu habis,
    coba lagi (half-open state).
    """

    def __init__(self, disable_duration: int = 3600):
        self._disabled: dict[str, float] = {}
        self._duration = disable_duration
        self._lock = asyncio.Lock()

    async def is_open(self, model_id: str) -> bool:
        """True kalau model sedang di-disable."""
        async with self._lock:
            if model_id not in self._disabled:
                return False

            elapsed = time.time() - self._disabled[model_id]
            if elapsed >= self._duration:
                # Half-open: bebaskan dan biarkan caller coba lagi
                del self._disabled[model_id]
                logger.info(f"[CircuitBreaker] 🔄 {model_id} dibebaskan, akan dicoba ulang")
                return False

            return True

    async def trip(self, model_id: str, reason: str = "") -> None:
        """Tandai model sebagai rusak."""
        async with self._lock:
            self._disabled[model_id] = time.time()
            logger.error(
                f"[CircuitBreaker] 🔴 {model_id} di-disable selama "
                f"{self._duration}s. Reason: {reason}"
            )

    async def reset(self, model_id: str | None = None) -> None:
        """Reset manual — semua atau spesifik model."""
        async with self._lock:
            if model_id:
                self._disabled.pop(model_id, None)
            else:
                self._disabled.clear()

    async def status(self) -> dict[str, float]:
        """Snapshot model yang sedang disabled (untuk debugging/health)."""
        async with self._lock:
            now = time.time()
            return {
                mid: round(self._duration - (now - ts), 1)
                for mid, ts in self._disabled.items()
            }