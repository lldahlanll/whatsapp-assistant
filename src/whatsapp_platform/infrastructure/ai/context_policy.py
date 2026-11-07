"""Pengatur aturan konteks (jumlah pesan lama, instruksi bot, dan alat bantu) sesuai topik pesan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from whatsapp_platform.infrastructure.ai.constants import (
    AI_FINANCE_GROUP_SYSTEM_PROMPT,
    AI_FINANCE_SYSTEM_PROMPT,
    AI_FULL_SYSTEM_PROMPT,
    AI_NETWORK_SYSTEM_PROMPT,
    AI_SYSTEM_PROMPT,
    IntentType,
)
from whatsapp_platform.infrastructure.ai.memory_tools import MEMORY_TOOLS, wants_memory_tools
from whatsapp_platform.infrastructure.ai.reminder_tools import REMINDER_TOOLS, wants_reminder_tools
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
        is_group: bool = False,
        memory_enabled: bool = False,
        reminders_enabled: bool = False,
    ) -> ContextPolicy:
        """Menentukan instruksi, jumlah riwayat pesan, dan alat yang dibutuhkan AI."""
        # Permintaan "ingat/lupakan" di obrolan biasa butuh tool → pakai intent "memory"
        # agar diarahkan ke model yang mendukung tool calling.
        wants_memory = memory_enabled and tools_enabled and wants_memory_tools(text)
        if wants_memory and intent in ("simple_chat", "chat"):
            intent = "memory"
        # "ingetin bayar listrik tiap tgl 5" juga terdeteksi sebagai finance (kata "bayar").
        # Pengingat diutamakan: prompt umum + hanya tool pengingat, agar tidak tercatat sebagai pengeluaran.
        wants_reminder = reminders_enabled and tools_enabled and wants_reminder_tools(text)
        if wants_reminder:
            intent = "memory"  # intent obrolan yang memakai model ber-tool calling

        # Determine history limit from env settings
        if intent == "simple_chat":
            history_limit = 0
        elif intent in ("chat", "memory"):
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
        if intent in ("simple_chat", "chat", "memory"):
            system_prompt = AI_SYSTEM_PROMPT
        elif intent == "finance":
            system_prompt = AI_FINANCE_GROUP_SYSTEM_PROMPT if is_group else AI_FINANCE_SYSTEM_PROMPT
        elif intent == "network":
            system_prompt = AI_NETWORK_SYSTEM_PROMPT
        elif intent == "full":
            system_prompt = AI_FULL_SYSTEM_PROMPT
        else:
            system_prompt = AI_SYSTEM_PROMPT

        # Resolve dynamic tools if tools are enabled
        tools = select_tools(intent, text) if tools_enabled else None
        if wants_memory:
            tools = [*(tools or []), *MEMORY_TOOLS]
        if wants_reminder:
            tools = [*(tools or []), *REMINDER_TOOLS]

        return ContextPolicy(
            intent=intent,
            history_limit=history_limit,
            system_prompt=system_prompt,
            tools=tools,
        )
