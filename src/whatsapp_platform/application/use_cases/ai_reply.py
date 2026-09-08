"""Alur kerja utama untuk membuat balasan AI dari pesan WhatsApp yang masuk."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.application.use_cases.get_conversation import (
    GetConversationHistoryUseCase,
)
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.constants import classify_intent
from whatsapp_platform.infrastructure.ai.context_policy import ContextPolicyManager
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse, ProviderMessage
from whatsapp_platform.infrastructure.config.settings import Settings

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.ai.composite_executor import CompositeToolExecutor
    from whatsapp_platform.infrastructure.mikrotik.tool_executor import MikroTikToolExecutor

logger = structlog.get_logger()

# Pola untuk mencegah manipulasi peran (role spoofing) pada pesan pengguna
_ROLE_SPOOF_PATTERN = re.compile(
    r"(?i)^(system|assistant|user|instruction|prompt)\s*:",
    re.MULTILINE,
)

_EMOJI_PATTERN = re.compile(
    r"[\U0001F000-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U00002300-\U000023FF"
    r"\U00002B50-\U00002B55"
    r"\U0000FE00-\U0000FE0F"
    r"\U0000200D]"
    r"+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Hapus icon atau emoji dari teks balasan agar jawaban bersih dan profesional."""
    if not text:
        return text
    cleaned = _EMOJI_PATTERN.sub("", text)
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
    return "\n".join(cleaned_lines).strip()


def _escape_role_spoof(text: str) -> str:
    return _ROLE_SPOOF_PATTERN.sub(lambda m: m.group(0).rstrip(":") + ":\u200b", text)


def _message_to_provider_role(msg: Message) -> ProviderMessage:
    text = msg.content.text if isinstance(msg.content, TextContent) else "[media]"
    text = _escape_role_spoof(text)

    if msg.direction == MessageDirection.OUTBOUND or msg.is_from_me:
        return ProviderMessage(role="assistant", content=text)

    sender_label = msg.push_name or msg.sender_jid.user
    return ProviderMessage(role="user", content=f"[{sender_label}]: {text}")


class AIReplyUseCase:
    """Memproses pesan, menyiapkan riwayat & alat bantu, lalu meminta balasan ke AI."""

    def __init__(
        self,
        ai_service: AIService,
        get_conv_uc: GetConversationHistoryUseCase,
        tool_executor: CompositeToolExecutor | MikroTikToolExecutor | None = None,
        context_window_messages: int = 20,
        max_context_chars: int = 16000,
        settings: Settings | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._get_conv_uc = get_conv_uc
        self._tool_executor = tool_executor
        self._context_window_messages = context_window_messages
        self._max_context_chars = max_context_chars
        self._settings = settings or Settings()

    async def execute(
        self,
        chat_jid_str: str,
        trigger_message: Message,
        model_override: str | None = None,
    ) -> AIResponse:
        """Generate an AI reply for the trigger message in the given chat."""
        trigger_text = (
            trigger_message.content.text
            if isinstance(trigger_message.content, TextContent)
            else ""
        )

        # 1. Intent classification BEFORE history fetch (with fallback guard)
        tools_available = bool(self._tool_executor and self._tool_executor.is_enabled)
        try:
            intent = classify_intent(trigger_text) if tools_available else "chat"
        except Exception as exc:
            logger.warning("Intent classification failed, falling back to 'chat'", error=str(exc))
            intent = "chat"

        # 2. Resolve ContextPolicy (system prompt, dynamic tools, history limit)
        policy = ContextPolicyManager.get_policy(
            intent=intent,
            text=trigger_text,
            settings=self._settings,
            tools_enabled=tools_available,
        )

        # 3. Fetch DB conversation history using policy.history_limit (with fallback guard)
        history: list[Message] = []
        if policy.history_limit > 0:
            try:
                history = await self._get_conv_uc.execute(
                    chat_jid_str, limit=policy.history_limit
                )
                history = list(reversed(history))  # oldest → newest
            except Exception as exc:
                logger.warning(
                    "Failed to fetch conversation history, proceeding without history",
                    chat=chat_jid_str,
                    error=str(exc),
                )
                history = []

        # Apply character-based truncation guard (C6)
        history = self._truncate_to_char_budget(history, chat_jid_str)

        logger.debug(
            "AI context policy resolved",
            chat=chat_jid_str,
            intent=policy.intent,
            history_count=len(history),
            tool_count=len(policy.tools) if policy.tools else 0,
        )

        messages: list[ProviderMessage] = [
            ProviderMessage(role="system", content=policy.system_prompt),
        ]

        # Add DB history (excludes the trigger message which is appended below)
        trigger_id = trigger_message.id
        for msg in history:
            if msg.id == trigger_id:
                continue
            messages.append(_message_to_provider_role(msg))

        # Add the trigger message as the final "user" turn
        sender_label = trigger_message.push_name or trigger_message.sender_jid.user
        display_trigger_text = trigger_text or "[media message]"
        messages.append(
            ProviderMessage(
                role="user",
                content=f"[{sender_label}]: {_escape_role_spoof(display_trigger_text)}",
            )
        )

        request_id = uuid.uuid4().hex[:12]

        # 4. Delegate to AIService with selected tools
        if policy.tools and self._tool_executor:
            response = await self._ai_service.generate_reply_with_tools(
                chat_jid=chat_jid_str,
                messages=messages,
                tool_executor=self._tool_executor,
                tools=policy.tools,
                user_jid=trigger_message.sender_jid,
                wa_chat_jid=trigger_message.chat_jid,
                model_override=model_override,
                max_tool_iterations=self._settings.ai_max_tool_iterations,
                max_tool_result_chars=self._settings.ai_max_tool_result_chars,
                intent=policy.intent,
                request_id=request_id,
            )
        else:
            response = await self._ai_service.generate_reply(
                chat_jid=chat_jid_str,
                messages=messages,
                model_override=model_override,
                intent=policy.intent,
                request_id=request_id,
            )

        # 5. Persist trigger and AI reply to the context cache
        await self._ai_service.append_to_context(
            chat_jid_str, "user", f"[{sender_label}]: {trigger_text}"
        )
        if response.text:
            response.text = strip_emojis(response.text)
            await self._ai_service.append_to_context(
                chat_jid_str, "assistant", response.text
            )

        return response


    def _truncate_to_char_budget(
        self, messages: list[Message], chat_jid_str: str
    ) -> list[Message]:
        """Trim oldest messages until total character count is within budget (C6).

        Applies AFTER the message-count cap in execute().  Iterates from the
        oldest end and drops messages until the remaining content fits.
        Logs when truncation occurs so it's visible in debugging.
        """
        total_chars = sum(
            len(m.content.text) if isinstance(m.content, TextContent) else 10
            for m in messages
        )

        if total_chars <= self._max_context_chars:
            return messages

        original_count = len(messages)
        while messages and total_chars > self._max_context_chars:
            dropped = messages.pop(0)  # remove oldest
            total_chars -= (
                len(dropped.content.text)
                if isinstance(dropped.content, TextContent)
                else 10
            )

        logger.info(
            "AI context truncated to fit character budget",
            chat=chat_jid_str,
            dropped_messages=original_count - len(messages),
            remaining_messages=len(messages),
            max_chars=self._max_context_chars,
            final_chars=total_chars,
        )
        return messages
