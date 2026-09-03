"""SetNameHandler for !setname command."""

import structlog

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()


class SetNameHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "setname"

    @property
    def description(self) -> str:
        return "Change group name (Usage: !setname Nama Baru)"

    async def handle(self, ctx: CommandContext) -> None:
        if not ctx.message.chat_jid.is_group:
            await ctx.reply(
                "❌ Command ini hanya dapat digunakan di dalam grup WhatsApp."
            )
            return

        if not ctx.group_mgmt_uc:
            await ctx.reply("❌ Fitur Group Management belum terkonfigurasi.")
            return

        new_name = " ".join(ctx.command.args)
        if not new_name:
            await ctx.reply(
                "⚠️ Harap masukkan nama baru untuk grup. Contoh: `!setname Grup Developer`"
            )
            return

        try:
            await ctx.group_mgmt_uc.change_group_name(ctx.message.chat_jid, new_name)
            await ctx.reply(f"✏️ Nama grup berhasil diubah menjadi: *{new_name}*")
        except Exception as exc:
            logger.error("change_group_name failed", chat=str(ctx.message.chat_jid), error=str(exc), exc_info=True)
            await ctx.reply(f"❌ Gagal mengubah nama grup: {exc}")
