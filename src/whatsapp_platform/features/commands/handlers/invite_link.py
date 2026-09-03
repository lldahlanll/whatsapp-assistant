"""InviteLinkHandler for !invitelink command."""

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext


class InviteLinkHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "invitelink"

    @property
    def description(self) -> str:
        return "Get group invite link (Group only)"

    async def handle(self, ctx: CommandContext) -> None:
        if not ctx.message.chat_jid.is_group:
            await ctx.reply(
                "❌ Command ini hanya dapat digunakan di dalam grup WhatsApp."
            )
            return

        if not ctx.group_mgmt_uc:
            await ctx.reply("❌ Fitur Group Management belum terkonfigurasi.")
            return

        args = ctx.command.args
        revoke = "revoke" in args if args else False
        link = await ctx.group_mgmt_uc.get_invite_link(
            ctx.message.chat_jid, revoke=revoke
        )
        if link:
            await ctx.reply(f"🔗 *LINK UNDANGAN GRUP*\n\n{link}")
        else:
            await ctx.reply("❌ Gagal mendapatkan link undangan grup.")
