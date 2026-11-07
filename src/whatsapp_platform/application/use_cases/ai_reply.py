"""Alur kerja utama untuk membuat balasan AI dari pesan WhatsApp yang masuk."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.application.use_cases.get_conversation import (
    GetConversationHistoryUseCase,
)
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.claim_guard import (
    UNBACKED_CLAIM_REPLY,
    UNBACKED_REMINDER_REPLY,
    is_unbacked_finance_claim,
    is_unbacked_reminder_claim,
)
from whatsapp_platform.infrastructure.ai.constants import (
    AI_IMAGE_DEFAULT_MIME_TYPE,
    AI_IMAGE_DEFAULT_PROMPT,
    IntentType,
    classify_intent,
)
from whatsapp_platform.infrastructure.ai.context_policy import ContextPolicyManager
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    ImagePart,
    ProviderMessage,
)
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.shared.utils.timezone import now_local

if TYPE_CHECKING:
    from whatsapp_platform.features.ai.memory_store import UserMemoryStore
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


def _current_date_note() -> str:
    """Tanggal lokal hari ini, agar LLM bisa menghitung 'kemarin', '3 hari lalu', dst."""
    today = now_local()
    return (
        f"Today is {today.strftime('%A')}, {today.strftime('%Y-%m-%d')} "
        "(Asia/Jakarta time, WIB). Resolve relative dates such as 'hari ini', 'kemarin', "
        "or '3 hari lalu' from this date."
    )


class _ToolRunRecorder:
    """Membungkus executor untuk satu giliran: mencatat tool yang sukses dijalankan."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.succeeded: set[str] = set()

    @property
    def is_enabled(self) -> bool:
        return bool(getattr(self._inner, "is_enabled", True))

    async def execute(self, tool_name: str, *args: Any, **kwargs: Any) -> str:
        result = await self._inner.execute(tool_name, *args, **kwargs)
        try:
            if json.loads(result).get("status") == "success":
                self.succeeded.add(tool_name)
        except (TypeError, ValueError, AttributeError):
            pass
        return result


def _escape_role_spoof(text: str) -> str:
    return _ROLE_SPOOF_PATTERN.sub(lambda m: m.group(0).rstrip(":") + ":\u200b", text)


def _extract_image(msg: Message) -> ImagePart | None:
    """Ambil gambar (bytes sudah diunduh handler) dari pesan pemicu, jika ada."""
    content = msg.content
    if (
        isinstance(content, MediaContent)
        and content.media_type == MediaType.IMAGE
        and content.file_bytes
    ):
        return ImagePart(
            data=content.file_bytes,
            mime_type=content.mime_type or AI_IMAGE_DEFAULT_MIME_TYPE,
        )
    return None


def _as_utc(ts: datetime) -> datetime:
    """Timestamp dari DB bisa naive (disimpan sebagai UTC)."""
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


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
        memory_store: UserMemoryStore | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._get_conv_uc = get_conv_uc
        self._tool_executor = tool_executor
        self._context_window_messages = context_window_messages
        self._max_context_chars = max_context_chars
        self._settings = settings or Settings()
        self._memory_store = memory_store if self._settings.ai_memory_enabled else None

    async def execute(
        self,
        chat_jid_str: str,
        trigger_message: Message,
        model_override: str | None = None,
        history_since: datetime | None = None,
    ) -> AIResponse:
        """Generate an AI reply for the trigger message in the given chat.

        history_since: pesan yang lebih lama dari waktu ini diabaikan (hasil !ai reset).
        """
        image = _extract_image(trigger_message)
        if isinstance(trigger_message.content, TextContent):
            trigger_text = trigger_message.content.text
        elif isinstance(trigger_message.content, MediaContent):
            trigger_text = trigger_message.content.caption or ""
        else:
            trigger_text = ""

        # 1. Intent classification BEFORE history fetch (with fallback guard)
        tools_available = bool(self._tool_executor and self._tool_executor.is_enabled)
        intent: IntentType
        if image is not None:
            # Gambar selalu ke intent "image" → 9router memakai model vision
            intent = "image"
        else:
            try:
                intent = classify_intent(trigger_text) if tools_available else "chat"
            except Exception as exc:
                logger.warning("Intent classification failed, falling back to 'chat'", error=str(exc))
                intent = "chat"

        # Dukung konfirmasi pendek (misal 'ya', 'oke', 'lanjut', 'hapus') setelah prompt konfirmasi
        if tools_available and intent == "chat" and trigger_text:
            clean_trigger = trigger_text.strip().lower()
            confirmation_words = {
                "ya", "iya", "y", "yes", "oke", "ok", "lanjut", "lanjutkan",
                "yakin", "benar", "betul", "setuju", "hapus", "batal", "batalkan",
                "tidak", "gak", "nggak", "no", "deal", "siap", "gas"
            }
            if clean_trigger in confirmation_words or len(clean_trigger.split()) <= 2:
                try:
                    recent = await self._get_conv_uc.execute(chat_jid_str, limit=2)
                    for prev_msg in recent:
                        if history_since is not None and _as_utc(prev_msg.timestamp) <= history_since:
                            continue
                        if prev_msg.direction == MessageDirection.OUTBOUND or prev_msg.is_from_me:
                            prev_txt = prev_msg.content.text if isinstance(prev_msg.content, TextContent) else ""
                            prev_low = prev_txt.lower()
                            if any(k in prev_low for k in ("konfirmasi", "yakin", "rekening", "transaksi", "saldo", "budget", "anggaran", "kategori", "hapus")):
                                intent = "finance"
                                logger.info("Inherited 'finance' intent from previous confirmation prompt", chat=chat_jid_str)
                                break
                            elif any(k in prev_low for k in ("mikrotik", "router", "interface", "reboot", "restart")):
                                intent = "network"
                                logger.info("Inherited 'network' intent from previous confirmation prompt", chat=chat_jid_str)
                                break
                except Exception as exc:
                    logger.debug("Failed to check confirmation context", error=str(exc))

        # 2. Resolve ContextPolicy (system prompt, dynamic tools, history limit)
        is_group = trigger_message.chat_jid.is_group
        policy = ContextPolicyManager.get_policy(
            intent=intent,
            text=trigger_text,
            settings=self._settings,
            tools_enabled=tools_available and image is None,
            is_group=is_group,
            memory_enabled=self._memory_store is not None,
            reminders_enabled=self._settings.scheduler_enabled,
        )

        # 3. Fetch DB conversation history using policy.history_limit (with fallback guard)
        history: list[Message] = []
        if policy.history_limit > 0:
            try:
                history = await self._get_conv_uc.execute(
                    chat_jid_str, limit=policy.history_limit
                )
                history = list(reversed(history))  # oldest → newest
                if history_since is not None:
                    history = [m for m in history if _as_utc(m.timestamp) > history_since]
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

        system_content = f"{policy.system_prompt}\n\n{_current_date_note()}"
        memory_block = await self._render_memory(chat_jid_str, trigger_message)
        if memory_block:
            system_content = f"{system_content}\n\n{memory_block}"
        messages: list[ProviderMessage] = [
            ProviderMessage(role="system", content=system_content),
        ]

        # Add DB history (excludes the trigger message which is appended below)
        trigger_id = trigger_message.id
        for msg in history:
            if msg.id == trigger_id:
                continue
            messages.append(_message_to_provider_role(msg))

        # Add the trigger message as the final "user" turn
        sender_label = trigger_message.push_name or trigger_message.sender_jid.user
        if image is not None:
            display_trigger_text = trigger_text or AI_IMAGE_DEFAULT_PROMPT
        else:
            display_trigger_text = trigger_text or "[media message]"
        messages.append(
            ProviderMessage(
                role="user",
                content=f"[{sender_label}]: {_escape_role_spoof(display_trigger_text)}",
                images=[image] if image is not None else None,
            )
        )

        request_id = uuid.uuid4().hex[:12]

        # 4. Delegate to AIService with selected tools
        recorder: _ToolRunRecorder | None = None
        if policy.tools and self._tool_executor:
            recorder = _ToolRunRecorder(self._tool_executor)
            response = await self._ai_service.generate_reply_with_tools(
                chat_jid=chat_jid_str,
                messages=messages,
                tool_executor=recorder,
                tools=policy.tools,
                user_jid=trigger_message.sender_jid,
                wa_chat_jid=trigger_message.chat_jid,
                model_override=model_override,
                max_tool_iterations=self._settings.ai_max_tool_iterations,
                max_tool_result_chars=self._settings.ai_max_tool_result_chars,
                intent=policy.intent,
                request_id=request_id,
                message_id=trigger_message.id,
                user_text=trigger_text,
            )
        else:
            response = await self._ai_service.generate_reply(
                chat_jid=chat_jid_str,
                messages=messages,
                model_override=model_override,
                intent=policy.intent,
                request_id=request_id,
            )
            # Tanpa tool, klaim "berhasil dicatat" untuk pesan finance pasti karangan LLM.
            if is_unbacked_finance_claim(trigger_text, response.text):
                logger.warning("Blocked unbacked finance success claim", chat=chat_jid_str, intent=policy.intent)
                response.text = UNBACKED_CLAIM_REPLY

        # Janji "pengingat diset" tanpa reminder_create yang sukses = pesan tidak akan pernah terkirim.
        reminder_saved = recorder is not None and "reminder_create" in recorder.succeeded
        if not reminder_saved and is_unbacked_reminder_claim(trigger_text, response.text):
            logger.warning("Blocked unbacked reminder claim", chat=chat_jid_str, intent=policy.intent)
            response.text = UNBACKED_REMINDER_REPLY

        # 5. Persist trigger and AI reply to the context cache
        # Bytes gambar tidak disimpan ke konteks; cukup penanda teks.
        context_text = f"[gambar] {trigger_text}".strip() if image is not None else trigger_text
        await self._ai_service.append_to_context(
            chat_jid_str, "user", f"[{sender_label}]: {context_text}"
        )
        if response.text:
            response.text = strip_emojis(response.text)
            await self._ai_service.append_to_context(
                chat_jid_str, "assistant", response.text
            )

        return response


    async def _render_memory(self, chat_jid_str: str, trigger_message: Message) -> str:
        """Blok memori pengguna untuk system prompt; gagal baca memori tidak menggagalkan balasan."""
        if self._memory_store is None:
            return ""
        try:
            block = await self._memory_store.render_for_prompt(
                chat_jid_str, str(trigger_message.sender_jid)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load user memory", chat=chat_jid_str, error=str(exc))
            return ""
        return _escape_role_spoof(block)

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
