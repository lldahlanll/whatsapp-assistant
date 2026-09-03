from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import ClassVar


class NetworkRateGuard:
    """Sliding-window rate limiter per user/chat and per tool."""

    DEFAULT_LIMITS: ClassVar[dict[str, int]] = {
        "NETWORK_HEALTH": 10,
        "NETWORK_TRAFFIC": 20,
        "NETWORK_SECURITY": 5,
        "NETWORK_LOGS": 5,
        "NETWORK_FIREWALL": 10,
        "NETWORK_DHCP": 15,
        "NETWORK_ROUTES": 10,
        "NETWORK_GENERAL": 10,
    }


    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        # {(user_key, tool_intent): [timestamps]}
        self._history: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_and_record(self, user_key: str, intent: str = "NETWORK_GENERAL") -> bool:
        """Check rate limit for the user and intent, recording timestamp if within limits."""
        limit = self.DEFAULT_LIMITS.get(intent, 10)
        now = time.monotonic()

        async with self._lock:
            timestamps = self._history[(user_key, intent)]
            # Purge timestamps outside the sliding window
            cutoff = now - self._window
            valid = [ts for ts in timestamps if ts > cutoff]
            self._history[(user_key, intent)] = valid

            if len(valid) >= limit:
                return False

            valid.append(now)
            return True
