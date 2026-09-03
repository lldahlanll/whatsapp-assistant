"""KickHandler for !kick command."""

import structlog

from whatsapp_platform.domain.exceptions.exceptions import InvalidJIDError
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()


class KickHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "kick"

    @property
    def description(self) -> str:
        return "Kick member from group (Usage: !kick 628xxx)"

    async def handle(self, ctx: CommandContext) -> None:
        if not ctx.message.chat_jid.is_group:
            await ctx.reply(
                "❌ Command ini hanya dapat digunakan di dalam grup WhatsApp."
            )
            return

        if not ctx.group_mgmt_uc:
            await ctx.reply("❌ Fitur Group Management belum terkonfigurasi.")
            return

        target_jid = ctx.message.quoted_sender_jid or (
            ctx.message.mentioned_jids[0] if ctx.message.mentioned_jids else None
        )
        if not target_jid and ctx.command.args:
            try:
                target_jid = JID.parse(ctx.command.args[0])
            except InvalidJIDError:
                logger.warning("Invalid JID format for kick target", raw=ctx.command.args[0])

        if not target_jid:
            await ctx.reply(
                "⚠️ Balas chat pengirim, tag @user, atau sertakan nomor HP. "
                "Contoh: `!kick @user` atau `!kick 6281234567890`"
            )
            return

        try:
            await ctx.group_mgmt_uc.kick_member(ctx.message.chat_jid, target_jid)
            await ctx.reply(f"✅ Berhasil mengeluarkan {target_jid.user} dari grup.")
        except Exception as exc:
            logger.error("kick_member failed", chat=str(ctx.message.chat_jid), error=str(exc), exc_info=True)
            await ctx.reply(f"❌ Gagal mengeluarkan anggota: {exc}")
