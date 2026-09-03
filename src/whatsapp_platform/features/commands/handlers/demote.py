"""DemoteHandler for !demote command."""

import structlog

from whatsapp_platform.domain.exceptions.exceptions import InvalidJIDError
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()


class DemoteHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "demote"

    @property
    def description(self) -> str:
        return "Demote Admin to regular member (Usage: !demote 628xxx)"

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
                logger.warning("Invalid JID format for demote target", raw=ctx.command.args[0])

        if not target_jid:
            await ctx.reply(
                "⚠️ Balas chat pengirim, tag @user, atau sertakan nomor HP. "
                "Contoh: `!demote @user` atau `!demote 6281234567890`"
            )
            return

        try:
            await ctx.group_mgmt_uc.demote_member(ctx.message.chat_jid, target_jid)
            await ctx.reply(
                f"🔽 Berhasil menurunkan {target_jid.user} dari Admin menjadi Anggota biasa."
            )
        except Exception as exc:
            logger.error("demote_member failed", chat=str(ctx.message.chat_jid), error=str(exc), exc_info=True)
            await ctx.reply(f"❌ Gagal menurunkan admin: {exc}")
