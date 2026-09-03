"""Pengatur aturan konteks (jumlah pesan lama, instruksi bot, dan alat bantu) sesuai topik pesan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from whatsapp_platform.infrastructure.ai.constants import (
    AI_FINANCE_SYSTEM_PROMPT,
    AI_FULL_SYSTEM_PROMPT,
    AI_NETWORK_SYSTEM_PROMPT,
    AI_SYSTEM_PROMPT,
    IntentType,
)
from whatsapp_platform.infrastructure.ai.tool_policy import select_tools

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.config.settings import Settings
    from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition


@dataclass(frozen=True)
class ContextPolicy:
    """Wadah aturan untuk satu permintaan balasan AI."""

    intent: IntentType
    history_limit: int
    system_prompt: str
    tools: list[ToolDefinition] | None


class ContextPolicyManager:
    """Pengelola untuk menentukan aturan konteks berdasarkan kategori pesan."""

    @classmethod
    def get_policy(
        cls,
        intent: IntentType,
        text: str,
        settings: Settings,
        tools_enabled: bool = True,
    ) -> ContextPolicy:
        """Menentukan instruksi, jumlah riwayat pesan, dan alat yang dibutuhkan AI."""
        # Determine history limit from env settings
        if intent == "simple_chat":
            history_limit = 0
        elif intent == "chat":
            history_limit = settings.ai_chat_history_limit
        elif intent == "finance":
            history_limit = settings.ai_finance_history_limit
        elif intent == "network":
            history_limit = settings.ai_network_history_limit
        elif intent == "full":
            history_limit = settings.ai_complex_history_limit
        else:
            history_limit = settings.ai_chat_history_limit

        # Resolve system prompt
        if intent in ("simple_chat", "chat"):
            system_prompt = AI_SYSTEM_PROMPT
        elif intent == "finance":
            system_prompt = AI_FINANCE_SYSTEM_PROMPT
        elif intent == "network":
            system_prompt = AI_NETWORK_SYSTEM_PROMPT
        elif intent == "full":
            system_prompt = AI_FULL_SYSTEM_PROMPT
        else:
            system_prompt = AI_SYSTEM_PROMPT

        # Resolve dynamic tools if tools are enabled
        tools = select_tools(intent, text) if tools_enabled else None

        return ContextPolicy(
            intent=intent,
            history_limit=history_limit,
            system_prompt=system_prompt,
            tools=tools,
        )
