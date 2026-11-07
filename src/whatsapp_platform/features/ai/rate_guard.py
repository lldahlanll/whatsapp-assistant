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
        per_user_max_requests: int | None = None,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # Batas per pengirim (hanya dipakai bila pemanggil menyertakan sender, mis. di grup) agar satu
        # anggota tidak menghabiskan kuota seluruh grup. None = nonaktif.
        self._per_user_max = per_user_max_requests
        # {chat_jid: deque of monotonic timestamps}
        self._windows: dict[str, deque[float]] = {}
        # {(chat_jid, sender): deque of monotonic timestamps}
        self._user_windows: dict[tuple[str, str], deque[float]] = {}
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

    async def check_and_record(self, chat_jid: str, sender: str | None = None) -> bool:
        """Atomically check throttle status and record if allowed.

        ``sender`` (opsional): jika diberikan dan ``per_user_max_requests`` diset, batas per pengirim
        juga diperiksa. Permintaan yang ditolak tidak dicatat di jendela mana pun.

        Returns True if the request is allowed (and was recorded),
        False if throttled (not recorded).
        """
        async with self._lock:
            if self._check_throttled(chat_jid):
                return False
            user_key = (chat_jid, sender) if sender and self._per_user_max else None
            if user_key is not None and self._user_throttled(user_key):
                return False
            now = time.monotonic()
            if chat_jid not in self._windows:
                self._windows[chat_jid] = deque()
            self._windows[chat_jid].append(now)
            if user_key is not None:
                self._user_windows.setdefault(user_key, deque()).append(now)
            return True

    def _user_throttled(self, user_key: tuple[str, str]) -> bool:
        """Internal check — caller must hold _lock."""
        window = self._user_windows.get(user_key)
        if not window:
            return False
        cutoff = time.monotonic() - self._window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        if not window:
            del self._user_windows[user_key]  # jangan biarkan dict tumbuh tanpa batas
            return False
        return len(window) >= (self._per_user_max or 0)

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
        if not window:
            del self._windows[chat_jid]
            return False
        return len(window) >= self._max_requests
