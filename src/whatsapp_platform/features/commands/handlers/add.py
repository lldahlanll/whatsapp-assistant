"""AddHandler for !add command."""

import structlog

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()


class AddHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "add"

    @property
    def description(self) -> str:
        return "Add member to group (Usage: !add 628xxx)"

    async def handle(self, ctx: CommandContext) -> None:
        if not ctx.message.chat_jid.is_group:
            await ctx.reply(
                "❌ Command ini hanya dapat digunakan di dalam grup WhatsApp."
            )
            return

        if not ctx.group_mgmt_uc:
            await ctx.reply("❌ Fitur Group Management belum terkonfigurasi.")
            return

        if not ctx.command.args:
            await ctx.reply(
                "⚠️ Harap sertakan nomor HP yang ingin ditambahkan. Contoh: `!add 6281234567890`"
            )
            return

        raw_target = ctx.command.args[0]
        try:
            target_jid = JID.parse(raw_target)
            await ctx.group_mgmt_uc.add_member(ctx.message.chat_jid, target_jid)
            await ctx.reply(f"✅ Berhasil menambahkan {target_jid.user} ke grup.")
        except Exception as exc:
            logger.error("add_member failed", chat=str(ctx.message.chat_jid), error=str(exc), exc_info=True)
            await ctx.reply(f"❌ Gagal menambahkan anggota: {exc}")
