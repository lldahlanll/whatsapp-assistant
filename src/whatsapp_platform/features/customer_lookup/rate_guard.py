"""Per-sender sliding-window rate guard for Customer Lookup requests."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class PerSenderRateGuard:
    """Sliding-window rate guard — tracks lookup timestamps per sender JID to prevent enumeration."""

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check_and_record(self, sender_jid: str) -> bool:
        """Atomically check throttle status and record if allowed.

        Args:
            sender_jid: String representation of sender JID.

        Returns:
            True if request is allowed (and recorded), False if rate-limited.
        """
        async with self._lock:
            if self._is_throttled(sender_jid):
                return False
            now = time.monotonic()
            if sender_jid not in self._windows:
                self._windows[sender_jid] = deque()
            self._windows[sender_jid].append(now)
            return True

    def _is_throttled(self, sender_jid: str) -> bool:
        now = time.monotonic()
        window = self._windows.get(sender_jid)
        if not window:
            return False
        cutoff = now - self._window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        return len(window) >= self._max_requests
