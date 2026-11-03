"""Eksekutor tool memory_* terhadap UserMemoryStore."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.features.ai.memory_store import MemoryRejectedError

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID
    from whatsapp_platform.features.ai.memory_store import UserMemoryStore

logger = structlog.get_logger()


class MemoryToolExecutor:
    """Menjalankan tool memory_* terhadap UserMemoryStore."""

    def __init__(self, memory_store: UserMemoryStore) -> None:
        self._store = memory_store

    @property
    def is_enabled(self) -> bool:
        return True

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
        message_id: str | None = None,
    ) -> str:
        chat_id, user_id = str(chat_jid), str(user_jid)
        try:
            if tool_name == "memory_save":
                entries = await self._store.add(chat_id, user_id, str(arguments.get("fact", "")))
                logger.info("Memory saved via AI tool", chat=chat_id, total=len(entries))
                return json.dumps({"status": "success", "saved": True, "total_memories": len(entries)})
            if tool_name == "memory_forget":
                removed = await self._store.remove(chat_id, user_id, str(arguments.get("query", "")))
                return json.dumps({"status": "success", "removed": removed}, ensure_ascii=False)
        except MemoryRejectedError as exc:
            return json.dumps({"status": "error", "error": exc.user_message}, ensure_ascii=False)

        return json.dumps({"status": "error", "error": f"Unknown memory tool '{tool_name}'."})
