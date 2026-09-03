"""In-memory async TTL cache for MikroTik queries."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class MikroTikCache:
    """Simple, thread-safe in-memory cache with per-key TTL."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Retrieve value if exists and not expired, else return None."""
        now = time.monotonic()
        async with self._lock:
            if key not in self._cache:
                return None
            expiry, value = self._cache[key]
            if now > expiry:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Store value with specified TTL."""
        expiry = time.monotonic() + ttl_seconds
        async with self._lock:
            self._cache[key] = (expiry, value)

    async def invalidate(self, key: str) -> None:
        """Manually invalidate a cache entry."""
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()
