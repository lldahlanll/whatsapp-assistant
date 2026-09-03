"""Per-chat AI configuration store.

Holds opt-in/opt-off state, per-chat model override, and whether the one-time
privacy notice has been sent. Uses an in-memory read-through cache backed by
AISQLiteStore for persistent storage across application restarts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.ai.sqlite_store import AISQLiteStore


@dataclass
class AIChatConfig:
    """Mutable configuration for one chat's AI feature."""

    enabled: bool = True
    model: str | None = None          # None = use provider default
    notice_sent: bool = False         # True after one-time privacy notice delivered



class AIChatConfigStore:
    """Thread-safe store for per-chat AI configuration with SQLite persistence.

    Lookups (get) are served from in-memory cache for sub-millisecond performance.
    Updates (set_enabled, set_model, mark_notice_sent) write to memory and persist
    to SQLite asynchronously.
    """

    def __init__(self, db_store: AISQLiteStore | None = None) -> None:
        self._configs: dict[str, AIChatConfig] = {}
        self._db_store = db_store
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Preload all configs from SQLite database into memory cache."""
        if self._db_store:
            loaded = await self._db_store.load_all_configs()
            async with self._lock:
                self._configs.update(loaded)

    async def get(self, chat_jid: str) -> AIChatConfig:
        """Return config for the given chat, creating and persisting a default if absent."""
        async with self._lock:
            if chat_jid not in self._configs:
                config = AIChatConfig()
                self._configs[chat_jid] = config
                if self._db_store:
                    await self._db_store.save_config(chat_jid, config)
            return self._configs[chat_jid]

    async def set_enabled(self, chat_jid: str, enabled: bool) -> None:
        async with self._lock:
            if chat_jid not in self._configs:
                self._configs[chat_jid] = AIChatConfig()
            self._configs[chat_jid].enabled = enabled
            config = self._configs[chat_jid]
        if self._db_store:
            await self._db_store.save_config(chat_jid, config)

    async def set_model(self, chat_jid: str, model: str | None) -> None:
        async with self._lock:
            if chat_jid not in self._configs:
                self._configs[chat_jid] = AIChatConfig()
            self._configs[chat_jid].model = model
            config = self._configs[chat_jid]
        if self._db_store:
            await self._db_store.save_config(chat_jid, config)

    async def mark_notice_sent(self, chat_jid: str) -> None:
        async with self._lock:
            if chat_jid not in self._configs:
                self._configs[chat_jid] = AIChatConfig()
            self._configs[chat_jid].notice_sent = True
            config = self._configs[chat_jid]
        if self._db_store:
            await self._db_store.save_config(chat_jid, config)
