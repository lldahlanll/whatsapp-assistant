"""AIChatCommandHandler for !ai commands (on, off, status, reset, model, stats)."""

from typing import cast

import structlog

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.constants import ALL_SUPPORTED_MODELS, SUPPORTED_MODELS
from whatsapp_platform.infrastructure.config.settings import Settings

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
    """

    def __init__(
        self, config_store: AIChatConfigStore, ai_service: AIService, settings: Settings | None = None
    ) -> None:
        self._config_store = config_store
        self._ai_service = ai_service
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
        return "Pengaturan AI Assistant (!ai on/off/status/reset/model/stats)"

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

    async def _handle_reset(self, ctx: CommandContext, chat_jid: str) -> None:
        # C7: !ai reset menandai waktu reset; AI mengabaikan history sebelum waktu ini.
        # Pesan di database WhatsApp tidak dihapus.
        await self._config_store.mark_context_reset(chat_jid)
        await self._ai_service.clear_context(chat_jid)
        await ctx.reply(
            "🧹 *Konteks Percakapan AI Di-reset*.\n"
            "Percakapan sebelumnya tidak lagi dipakai AI. (Pesan di database tetap tersimpan)."
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
