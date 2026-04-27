import asyncio
import weakref
from contextlib import asynccontextmanager
from typing import Optional

from loguru import logger


class JIDLockManager:
    """
    Provides per-JID asyncio.Lock dengan auto-GC via weakref.

    Design choices:
    - WeakValueDictionary: lock yang tidak ada pemegang aktif → auto di-GC
    - Meta-lock: protect dict creation race condition
    - Optional timeout: cegah deadlock kalau ada bug di critical section
    - Counter: untuk monitoring berapa lock aktif

    Usage:
        async with lock_manager.acquire(jid):
            # critical section — sequential per JID
            ...

        # atau dengan timeout (recommended untuk production)
        async with lock_manager.acquire(jid, timeout=120.0):
            ...
    """

    def __init__(self, default_timeout: Optional[float] = 120.0) -> None:
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._meta_lock = asyncio.Lock()
        self._default_timeout = default_timeout
        # Observability
        self._waiting_count: dict[str, int] = {}

    async def _get_lock(self, jid: str) -> asyncio.Lock:
        async with self._meta_lock:
            lock = self._locks.get(jid)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[jid] = lock
            return lock

    @asynccontextmanager
    async def acquire(
        self,
        jid: str,
        timeout: Optional[float] = None,
    ):
        """
        Acquire lock untuk JID tertentu.

        Args:
            jid: WhatsApp ID
            timeout: max wait dalam detik. None = pakai default,
                     0 atau negative = no timeout.

        Raises:
            asyncio.TimeoutError: kalau gagal acquire dalam timeout
        """
        lock = await self._get_lock(jid)
        effective_timeout = timeout if timeout is not None else self._default_timeout

        # Track waiting count untuk observability
        self._waiting_count[jid] = self._waiting_count.get(jid, 0) + 1

        try:
            if effective_timeout and effective_timeout > 0:
                try:
                    await asyncio.wait_for(lock.acquire(), timeout=effective_timeout)
                except asyncio.TimeoutError:
                    logger.error(
                        f"[LockManager] ⏱️ Timeout acquiring lock for {jid} "
                        f"(waited {effective_timeout}s, {self._waiting_count[jid]} waiting)"
                    )
                    raise
            else:
                await lock.acquire()

            try:
                if self._waiting_count[jid] > 1:
                    logger.debug(
                        f"[LockManager] 🔒 {jid} acquired "
                        f"({self._waiting_count[jid] - 1} still waiting)"
                    )
                yield
            finally:
                lock.release()
        finally:
            self._waiting_count[jid] -= 1
            if self._waiting_count[jid] <= 0:
                del self._waiting_count[jid]

    def stats(self) -> dict:
        """Snapshot untuk debugging / health endpoint."""
        return {
            "active_locks": len(self._locks),
            "waiting_jids": len(self._waiting_count),
            "total_waiters": sum(self._waiting_count.values()),
        }


jid_lock_manager = JIDLockManager()