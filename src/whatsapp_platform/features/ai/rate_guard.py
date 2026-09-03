"""Per-chat sliding-window rate guard for AI requests.

Prevents one chat from exhausting all provider keys by enforcing
a maximum of max_requests AI calls per window_seconds per chat,
independently of any provider-side rate limiting.

Uses collections.deque for O(1) amortised append/pop.
The asyncio.Lock makes it safe for concurrent coroutines.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class PerChatRateGuard:
    """Sliding-window rate guard — tracks recent AI call timestamps per chat."""

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # {chat_jid: deque of monotonic timestamps}
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def is_throttled(self, chat_jid: str) -> bool:
        """Return True if the chat has exceeded the request limit.

        Cleans stale timestamps before checking — purely sliding window, no reset.
        Does NOT record a new call (call record() separately on success).
        """
        async with self._lock:
            return self._check_throttled(chat_jid)

    async def record(self, chat_jid: str) -> None:
        """Record one AI call for the given chat."""
        async with self._lock:
            now = time.monotonic()
            if chat_jid not in self._windows:
                self._windows[chat_jid] = deque()
            self._windows[chat_jid].append(now)

    async def check_and_record(self, chat_jid: str) -> bool:
        """Atomically check throttle status and record if allowed.

        Returns True if the request is allowed (and was recorded),
        False if throttled (not recorded).
        """
        async with self._lock:
            if self._check_throttled(chat_jid):
                return False
            now = time.monotonic()
            if chat_jid not in self._windows:
                self._windows[chat_jid] = deque()
            self._windows[chat_jid].append(now)
            return True

    def _check_throttled(self, chat_jid: str) -> bool:
        """Internal check — caller must hold _lock."""
        now = time.monotonic()
        window = self._windows.get(chat_jid)
        if not window:
            return False
        # Evict timestamps outside the sliding window
        cutoff = now - self._window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        return len(window) >= self._max_requests
