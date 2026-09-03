"""Pengelola kunci API untuk penyedia AI.

Mengatur pergantian kunci secara bergantian dan mengistirahatkan kunci
yang terkena batasan limit (rate limit).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class _KeyState:
    """Status istirahat (cooldown) untuk satu kunci API."""

    cooldown_until: float = 0.0  # waktu detik; 0 berarti kunci siap digunakan


class KeyPool:
    """Mengelola daftar kunci API dan perputarannya secara aman."""

    def __init__(self, keys: list[str], default_cooldown_seconds: float = 60.0) -> None:
        if not keys:
            raise ValueError("KeyPool requires at least one API key")
        self._keys: list[str] = keys
        self._states: list[_KeyState] = [_KeyState() for _ in keys]
        self._default_cooldown: float = default_cooldown_seconds
        self._lock = asyncio.Lock()
        self._cursor: int = 0  # round-robin cursor, advances on each key pick

    def size(self) -> int:
        """Number of keys in the pool — used by AIService for bounded retry loops (C5)."""
        return len(self._keys)

    async def next_available_key(self) -> tuple[int, str] | None:
        """Return (index, key) for the next non-cooling key, or None if all cooling.

        Uses a round-robin cursor so load is spread across keys rather than
        always hammering key[0].
        """
        async with self._lock:
            now = time.monotonic()
            n = len(self._keys)
            for offset in range(n):
                idx = (self._cursor + offset) % n
                if self._states[idx].cooldown_until <= now:
                    self._cursor = (idx + 1) % n
                    return (idx, self._keys[idx])
            return None

    async def mark_rate_limited(
        self, index: int, retry_after_seconds: float | None = None
    ) -> None:
        """Mark key[index] as rate-limited until cooldown expires.

        Args:
            index: Key index (0-based).
            retry_after_seconds: Cooldown duration from provider.
                If None or ≤0, falls back to the pool's default_cooldown_seconds.
        """
        duration = (
            retry_after_seconds
            if retry_after_seconds and retry_after_seconds > 0
            else self._default_cooldown
        )
        async with self._lock:
            self._states[index].cooldown_until = time.monotonic() + duration

    async def is_all_cooling(self) -> bool:
        """Return True if every key is currently in cooldown."""
        async with self._lock:
            now = time.monotonic()
            return all(s.cooldown_until > now for s in self._states)

    async def all_cooling_until(self) -> float:
        """Return the latest cooldown_until timestamp across all keys.

        Used by AIService to set the provider circuit-breaker expiry.
        Callers should only use this after confirming is_all_cooling() is True.
        """
        async with self._lock:
            return max(s.cooldown_until for s in self._states)

    async def cooldown_until_for(self, index: int) -> float:
        """Return the cooldown_until for a specific key (used in tests / stats)."""
        async with self._lock:
            return self._states[index].cooldown_until

    async def get_cooling_keys(self) -> list[int]:
        """Return list of indices currently in cooldown (for !ai stats / observability)."""
        async with self._lock:
            now = time.monotonic()
            return [i for i, s in enumerate(self._states) if s.cooldown_until > now]
