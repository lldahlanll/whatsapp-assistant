"""GroupInfoHandler for !groupinfo command."""

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext


class GroupInfoHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "groupinfo"

    @property
    def description(self) -> str:
        return "Display group metadata and info (Group only)"

    async def handle(self, ctx: CommandContext) -> None:
        if not ctx.message.chat_jid.is_group:
            await ctx.reply(
                "❌ Command ini hanya dapat digunakan di dalam grup WhatsApp."
            )
            return

        if not ctx.group_mgmt_uc:
            await ctx.reply("❌ Fitur Group Management belum terkonfigurasi.")
            return

        info = await ctx.group_mgmt_uc.get_group_info(ctx.message.chat_jid)
        name = info.get("name") or "Grup Tanpa Nama"
        owner_raw = info.get("owner") or "Tidak diketahui"
        owner_display = owner_raw.split("@")[0] if "@" in owner_raw else owner_raw
        if owner_display and owner_display != "Tidak diketahui":
            owner_display = f"+{owner_display}"

        topic = info.get("topic") or "-"
        participants = info.get("participants", [])

        # Format member list
        member_lines = []
        for idx, p in enumerate(participants, 1):
            if isinstance(p, dict):
                phone = p.get("phone") or "Unknown"
                name_str = f" ({p['display_name']})" if p.get("display_name") else ""

                badge = ""
                if p.get("is_super_admin"):
                    badge = " 👑 [Pembuat]"
                elif p.get("is_admin"):
                    badge = " 🛡️ [Admin]"

                member_lines.append(f"{idx}. +{phone}{name_str}{badge}")
            else:
                p_str = str(p).split("@")[0]
                member_lines.append(f"{idx}. +{p_str}")

        members_formatted = (
            "\n".join(member_lines) if member_lines else "Tidak ada data anggota."
        )

        resp = (
            f"👥 *INFORMASI GRUP WHATSAPP*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *Nama Grup*: {name}\n"
            f"🆔 *ID Grup*: `{ctx.message.chat_jid.user}`\n"
            f"👑 *Pembuat*: {owner_display}\n"
            f"📝 *Deskripsi*: {topic}\n"
            f"👥 *Total Anggota*: {len(participants)} orang\n\n"
            f"📋 *DAFTAR ANGGOTA GRUP*:\n"
            f"{members_formatted}\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        await ctx.reply(resp)
