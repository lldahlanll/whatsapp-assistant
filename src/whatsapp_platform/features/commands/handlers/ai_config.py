"""AIChatCommandHandler for !ai commands (on, off, status, reset, model, stats, memori, ringkasan)."""

from typing import TYPE_CHECKING, cast

import structlog

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.memory_store import MemoryRejectedError, UserMemoryStore
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.constants import ALL_SUPPORTED_MODELS, SUPPORTED_MODELS
from whatsapp_platform.infrastructure.config.settings import Settings

if TYPE_CHECKING:
    from whatsapp_platform.features.ai.conversation_summary import ConversationSummarizer

logger = structlog.get_logger()

# Sub-command yang mengubah konfigurasi atau membuka data pemakaian: khusus admin.
_ADMIN_SUBCOMMANDS = frozenset({"on", "off", "reset", "model", "stats"})

_ADMIN_ONLY_TEXT = (
    "⛔ Perintah ini khusus admin bot.\n"
    "Admin diatur lewat `AI_ADMIN_JIDS` di file .env (nomor WhatsApp, pisahkan dengan koma)."
)


class AIChatCommandHandler(BaseCommandHandler):
    """Handler for '!ai' configuration and management commands.

    Sub-commands:
    - !ai on            : Enable AI auto-reply for this chat (sends 1-time privacy notice)
    - !ai off           : Disable AI auto-reply for this chat
    - !ai status        : Display current AI status and model configuration
    - !ai reset         : Clear LLM conversation context (does NOT delete DB messages)
    - !ai model <name>  : Set per-chat model override (validated against whitelist)
    - !ai stats         : Display daily LLM usage counters and key pool status
    - !ai memori        : Tampilkan memori AI milik pengirim di chat ini
    - !ai ingat <fakta> : Simpan fakta ke memori pengirim
    - !ai lupa <n|teks|semua> : Hapus memori pengirim
    """

    def __init__(
        self,
        config_store: AIChatConfigStore,
        ai_service: AIService,
        settings: Settings | None = None,
        memory_store: UserMemoryStore | None = None,
        summarizer: "ConversationSummarizer | None" = None,
    ) -> None:
        self._summarizer = summarizer
        self._config_store = config_store
        self._ai_service = ai_service
        self._memory_store = memory_store
        self._admin_jids = set(cast(list[str], settings.ai_admin_jids)) if settings else set()
        if not self._admin_jids:
            logger.warning("AI_ADMIN_JIDS kosong: tidak ada yang bisa menjalankan !ai on/off/reset/model/stats")

    def _is_admin(self, msg: Message) -> bool:
        """Admin = pengirim yang terdaftar di AI_ADMIN_JIDS (nomor atau JID lengkap).

        Pesan dari nomor bot sendiri tidak pernah sampai ke sini (router mengabaikan is_from_me).
        """
        sender = msg.sender_jid
        return str(sender) in self._admin_jids or sender.user in self._admin_jids

    @property
    def command_name(self) -> str:
        return "ai"

    @property
    def description(self) -> str:
        return "Pengaturan AI Assistant (!ai on/off/status/reset/model/stats/memori)"

    async def handle(self, ctx: CommandContext) -> None:
        args = ctx.command.args
        chat_jid_str = str(ctx.message.chat_jid)

        if not args:
            await ctx.reply(
                "🤖 *PANDUAN BOT AI*\n"
                "-----------------------------------\n"
                "• `!ai on` - Aktifkan AI di chat ini\n"
                "• `!ai off` - Nonaktifkan AI di chat ini\n"
                "• `!ai status` - Cek status AI & model\n"
                "• `!ai reset` - Reset konteks percakapan AI\n"
                "• `!ai model <nama>` - Ganti model AI\n"
                "• `!ai stats` - Cek statistik penggunaan LLM\n"
                "• `!ai memori` - Lihat hal yang diingat AI tentangmu\n"
                "• `!ai ingat <fakta>` - Minta AI mengingat sesuatu\n"
                "• `!ai lupa <nomor|teks|semua>` - Hapus memori AI\n"
                "• `!ai ringkasan` - Lihat ringkasan obrolan yang dipakai AI di chat ini\n"
                "-----------------------------------"
            )
            return

        sub_command = args[0].lower()

        if sub_command in _ADMIN_SUBCOMMANDS and not self._is_admin(ctx.message):
            logger.info(
                "Rejected non-admin !ai command",
                sub_command=sub_command,
                sender=str(ctx.message.sender_jid),
                chat=chat_jid_str,
            )
            await ctx.reply(_ADMIN_ONLY_TEXT)
            return

        if sub_command == "on":
            await self._handle_on(ctx, chat_jid_str)
        elif sub_command == "off":
            await self._handle_off(ctx, chat_jid_str)
        elif sub_command == "status":
            await self._handle_status(ctx, chat_jid_str)
        elif sub_command == "reset":
            await self._handle_reset(ctx, chat_jid_str)
        elif sub_command == "model":
            model_name = args[1] if len(args) > 1 else ""
            await self._handle_model(ctx, chat_jid_str, model_name)
        elif sub_command == "stats":
            await self._handle_stats(ctx)
        elif sub_command in ("memori", "memory"):
            await self._handle_memory_list(ctx, chat_jid_str)
        elif sub_command == "ingat":
            await self._handle_memory_add(ctx, chat_jid_str, " ".join(args[1:]))
        elif sub_command == "lupa":
            await self._handle_memory_forget(ctx, chat_jid_str, " ".join(args[1:]))
        elif sub_command in ("ringkasan", "summary"):
            await self._handle_summary(ctx, chat_jid_str, args[1:])
        else:
            await ctx.reply(f"❌ Sub-command `!ai {sub_command}` tidak dikenali. Ketik `!ai` untuk bantuan.")

    async def _handle_on(self, ctx: CommandContext, chat_jid: str) -> None:
        config = await self._config_store.get(chat_jid)
        await self._config_store.set_enabled(chat_jid, True)

        response = "✅ *AI Auto-Reply Diaktifkan* untuk chat ini."

        # Send one-time privacy notice if not sent previously
        if not config.notice_sent:
            await self._config_store.mark_notice_sent(chat_jid)
            response += (
                "\n\n🔒 *Pemberitahuan Privasi*:\n"
                "Pesan dalam chat ini akan dikirimkan ke provider LLM pihak ketiga "
                "(Gemini / Groq / OpenRouter) untuk menghasilkan balasan AI."
            )

        await ctx.reply(response)

    async def _handle_memory_list(self, ctx: CommandContext, chat_jid: str) -> None:
        if self._memory_store is None:
            await ctx.reply("ℹ️ Fitur memori AI sedang dinonaktifkan.")
            return
        entries = await self._memory_store.get_all(chat_jid, str(ctx.message.sender_jid))
        if not entries:
            await ctx.reply(
                "🧠 Belum ada yang AI ingat tentangmu di chat ini.\n"
                "Contoh: `!ai ingat panggil aku Mas Dahlan`"
            )
            return
        lines = "\n".join(f"{i}. {entry}" for i, entry in enumerate(entries, start=1))
        await ctx.reply(
            "🧠 *MEMORI AI TENTANGMU*\n"
            "-----------------------------------\n"
            f"{lines}\n"
            "-----------------------------------\n"
            "Hapus dengan `!ai lupa <nomor>` atau `!ai lupa semua`."
        )

    async def _handle_memory_add(self, ctx: CommandContext, chat_jid: str, fact: str) -> None:
        if self._memory_store is None:
            await ctx.reply("ℹ️ Fitur memori AI sedang dinonaktifkan.")
            return
        if not fact.strip():
            await ctx.reply("Format: `!ai ingat <fakta>`, contoh: `!ai ingat aku vegetarian`")
            return
        try:
            entries = await self._memory_store.add(chat_jid, str(ctx.message.sender_jid), fact)
        except MemoryRejectedError as exc:
            await ctx.reply(f"❌ {exc.user_message}")
            return
        await ctx.reply(f"✅ Oke, sudah kuingat. ({len(entries)} catatan memori)")

    async def _handle_memory_forget(self, ctx: CommandContext, chat_jid: str, query: str) -> None:
        if self._memory_store is None:
            await ctx.reply("ℹ️ Fitur memori AI sedang dinonaktifkan.")
            return
        user_id = str(ctx.message.sender_jid)
        query = query.strip()
        if not query:
            await ctx.reply("Format: `!ai lupa <nomor|teks|semua>`. Lihat nomornya dengan `!ai memori`.")
            return
        if query.lower() in ("semua", "all"):
            count = await self._memory_store.clear(chat_jid, user_id)
            await ctx.reply(f"🧹 {count} catatan memori dihapus.")
            return
        removed = await self._memory_store.remove(chat_jid, user_id, query)
        if not removed:
            await ctx.reply("❌ Tidak ada memori yang cocok. Cek daftar dengan `!ai memori`.")
            return
        await ctx.reply("🗑️ Dihapus dari memori:\n" + "\n".join(f"• {e}" for e in removed))

    async def _handle_off(self, ctx: CommandContext, chat_jid: str) -> None:
        await self._config_store.set_enabled(chat_jid, False)
        await ctx.reply("🔴 *AI Auto-Reply Dinonaktifkan* untuk chat ini.")

    async def _handle_status(self, ctx: CommandContext, chat_jid: str) -> None:
        config = await self._config_store.get(chat_jid)
        provider_status = await self._ai_service.get_provider_status()

        status_icon = "🟢 AKTIF" if config.enabled else "🔴 NONAKTIF"
        model_str = config.model or "Default Provider"

        providers_info = []
        for name, info in provider_status.items():
            avail = info["available_keys"]
            tot = info["total_keys"]
            cb = " ⚠️ Circuit Broken" if info["circuit_breaker_active"] else ""
            providers_info.append(f"  • *{name.capitalize()}*: {avail}/{tot} key aktif{cb}")

        providers_formatted = "\n".join(providers_info) if providers_info else "  Tidak ada provider terkonfigurasi."

        text = (
            "🤖 *STATUS AI CHAT*\n"
            "-----------------------------------\n"
            f"• *Status*: {status_icon}\n"
            f"• *Model*: `{model_str}`\n"
            f"• *Pemberitahuan Privasi*: {'Sudah Dikirim' if config.notice_sent else 'Belum'}\n\n"
            "📡 *Status Provider LLM*:\n"
            f"{providers_formatted}\n"
            "-----------------------------------"
        )
        await ctx.reply(text)

    async def _handle_summary(self, ctx: CommandContext, chat_jid: str, rest: list[str]) -> None:
        if self._summarizer is None:
            await ctx.reply("ℹ️ Fitur ringkasan obrolan sedang dinonaktifkan.")
            return
        if rest and rest[0].lower() in ("hapus", "reset", "clear"):
            if not self._is_admin(ctx.message):
                await ctx.reply(_ADMIN_ONLY_TEXT)
                return
            await self._summarizer.clear(chat_jid)
            await ctx.reply("🧹 Ringkasan obrolan di chat ini dihapus. AI akan membuat ringkasan baru seiring obrolan.")
            return
        config = await self._config_store.get(chat_jid)
        summary = self._summarizer.get(chat_jid, config.context_reset_at)
        if not summary:
            await ctx.reply(
                "ℹ️ Belum ada ringkasan obrolan di chat ini. Ringkasan dibuat otomatis setelah obrolan "
                "cukup panjang."
            )
            return
        await ctx.reply(f"*Ringkasan obrolan yang diingat AI:*\n\n{summary}")

    async def _handle_reset(self, ctx: CommandContext, chat_jid: str) -> None:
        # C7: !ai reset menandai waktu reset; AI mengabaikan history sebelum waktu ini.
        # Pesan di database WhatsApp tidak dihapus.
        await self._config_store.mark_context_reset(chat_jid)
        await self._ai_service.clear_context(chat_jid)
        if self._summarizer is not None:
            await self._summarizer.clear(chat_jid)
        await ctx.reply(
            "🧹 *Konteks Percakapan AI Di-reset*.\n"
            "Percakapan sebelumnya tidak lagi dipakai AI. (Pesan di database tetap tersimpan).\n"
            "Memori jangka panjang tidak ikut terhapus; gunakan `!ai lupa semua` untuk itu."
        )

    async def _handle_model(self, ctx: CommandContext, chat_jid: str, model_name: str) -> None:
        if not model_name:
            supported_formatted = []
            for p, models in SUPPORTED_MODELS.items():
                supported_formatted.append(f"*{p.capitalize()}*:\n  " + "\n  ".join(f"`{m}`" for m in models))

            text = (
                "🎯 *MODEL AI SAAT INI*\n"
                f"Model override untuk chat ini: `{ (await self._config_store.get(chat_jid)).model or 'Default' }`\n\n"
                "📋 *Daftar Model Yang Didukung*:\n" + "\n\n".join(supported_formatted) + "\n\n"
                "Gunakan `!ai model <nama_model>` atau `!ai model reset` untuk mengembalikan ke default."
            )
            await ctx.reply(text)
            return

        if model_name.lower() in ("reset", "default"):
            await self._config_store.set_model(chat_jid, None)
            await ctx.reply("✅ Model AI dikembalikan ke default provider.")
            return

        # C9: Validate against SUPPORTED_MODELS whitelist
        if model_name not in ALL_SUPPORTED_MODELS:
            await ctx.reply(
                f"❌ Model `{model_name}` tidak didukung atau tidak ada di whitelist.\n"
                "Ketik `!ai model` untuk melihat daftar model yang tersedia."
            )
            return

        await self._config_store.set_model(chat_jid, model_name)
        await ctx.reply(f"✅ Model AI untuk chat ini diubah menjadi: `{model_name}`")

    async def _handle_stats(self, ctx: CommandContext) -> None:
        usage = await self._ai_service.usage_counter.get_stats()
        provider_status = await self._ai_service.get_provider_status()

        usage_lines = []
        for provider, dates in usage.items():
            for date, count in dates.items():
                usage_lines.append(f"  • *{provider.capitalize()}* ({date}): {count} panggilan")

        usage_str = "\n".join(usage_lines) if usage_lines else "  Belum ada panggilan hari ini."

        status_lines = []
        for name, info in provider_status.items():
            status_lines.append(
                f"  • *{name.capitalize()}*: {info['available_keys']}/{info['total_keys']} key aktif"
            )
        status_str = "\n".join(status_lines) if status_lines else "  - "

        text = (
            "📊 *STATISTIK PENGGUNAAN AI LLM*\n"
            "-----------------------------------\n"
            "📈 *Panggilan Hari Ini*:\n"
            f"{usage_str}\n\n"
            "🔑 *Ketersediaan Key Pool*:\n"
            f"{status_str}\n"
            "-----------------------------------"
        )
        await ctx.reply(text)
