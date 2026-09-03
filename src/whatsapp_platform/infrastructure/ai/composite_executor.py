"""Pengarah (router) untuk menjalankan fitur tambahan AI
berdasarkan awalan nama fitur (misal: mikrotik_ atau finance_).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID

logger = structlog.get_logger()


class CompositeToolExecutor:
    """Mengarahkan perintah fitur ke eksekutor yang sesuai."""

    def __init__(self) -> None:
        self._executors: dict[str, Any] = {}

    def register(self, prefix: str, executor: Any) -> None:
        self._executors[prefix] = executor
        logger.info("Registered tool executor", prefix=prefix)

    @property
    def is_enabled(self) -> bool:
        return bool(self._executors)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
    ) -> str:
        prefix = tool_name.split("_")[0] if "_" in tool_name else tool_name

        executor = self._executors.get(prefix)
        if executor is None:
            logger.warning("No executor found for tool", tool=tool_name, prefix=prefix)
            return json.dumps({
                "status": "error",
                "error": f"No executor registered for tool '{tool_name}'.",
            })

        return await executor.execute(
            tool_name=tool_name,
            arguments=arguments,
            user_jid=user_jid,
            chat_jid=chat_jid,
        )
