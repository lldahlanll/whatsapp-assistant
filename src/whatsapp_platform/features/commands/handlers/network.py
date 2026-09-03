"""NetworkCommandHandler for !network / !net commands."""

from __future__ import annotations

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.network.formatter import (
    format_dhcp_report,
    format_firewall_report,
    format_health_report,
    format_logs_report,
    format_network_error,
    format_security_report,
    format_traffic_report,
)
from whatsapp_platform.features.network.permission import NetworkPermissionChecker
from whatsapp_platform.features.network.rate_guard import NetworkRateGuard
from whatsapp_platform.infrastructure.mikrotik.exceptions import MikroTikDisabledError, MikroTikPermissionError
from whatsapp_platform.infrastructure.mikrotik.toolbox import NetworkToolbox


class NetworkCommandHandler(BaseCommandHandler):
    """Handler for '!network' and '!net' command shortcuts."""

    def __init__(
        self,
        toolbox: NetworkToolbox,
        permission_checker: NetworkPermissionChecker,
        rate_guard: NetworkRateGuard,
    ) -> None:
        self._toolbox = toolbox
        self._permission_checker = permission_checker
        self._rate_guard = rate_guard

    @property
    def command_name(self) -> str:
        return "network"

    @property
    def description(self) -> str:
        return "Monitoring & Audit MikroTik (!network health/traffic/security/dhcp/firewall/logs)"

    async def handle(self, ctx: CommandContext) -> None:
        sender_jid = ctx.message.sender_jid
        chat_jid = ctx.message.chat_jid
        user_jid_str = str(sender_jid)

        if not self._permission_checker.has_network_read_permission(sender_jid, chat_jid):
            await ctx.reply(format_network_error(MikroTikPermissionError()))
            return

        if not self._toolbox.is_enabled:
            await ctx.reply(format_network_error(MikroTikDisabledError()))
            return

        args = ctx.command.args
        if not args or args[0].lower() in ("help", "bantuan"):
            await ctx.reply(
                "📡 *PANDUAN PERINTAH NETWORK AI*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "• `!network health` - Cek kesehatan & status router\n"
                "• `!network traffic [iface]` - Monitor traffic interface/WAN\n"
                "• `!network security` - Audit keamanan & celah router\n"
                "• `!network dhcp [cari]` - Daftar perangkat terhubung\n"
                "• `!network firewall` - Ringkasan filter rules & NAT\n"
                "• `!network routes` - Cek jalur routing internet\n"
                "• `!network logs [topik]` - Log aktivitas terbaru\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "💡 _Anda juga bisa bertanya langsung via bahasa natural "
                "(e.g. 'cek mikrotik', 'traffic wan', 'cek security')._"
            )
            return

        sub_cmd = args[0].lower()
        sub_arg = args[1] if len(args) > 1 else None

        allowed = await self._rate_guard.check_and_record(user_jid_str, f"NETWORK_{sub_cmd.upper()}")
        if not allowed:
            await ctx.reply("⚠️ *Rate limit tercapai*. Silakan tunggu beberapa saat.")
            return

        try:
            if sub_cmd in ("health", "status", "kondisi"):
                report = await self._toolbox.get_health_report(user_jid=user_jid_str)
                await ctx.reply(format_health_report(report))

            elif sub_cmd in ("traffic", "bandwidth"):
                report = await self._toolbox.get_traffic_report(interface_name=sub_arg, user_jid=user_jid_str)
                await ctx.reply(format_traffic_report(report))

            elif sub_cmd in ("security", "audit"):
                report = await self._toolbox.get_security_report(user_jid=user_jid_str)
                await ctx.reply(format_security_report(report))

            elif sub_cmd in ("dhcp", "leases", "client"):
                leases = await self._toolbox.get_dhcp_report(query=sub_arg, user_jid=user_jid_str)
                await ctx.reply(format_dhcp_report(leases))

            elif sub_cmd in ("firewall", "filter", "nat"):
                report = await self._toolbox.get_firewall_report(user_jid=user_jid_str)
                await ctx.reply(format_firewall_report(report))

            elif sub_cmd in ("routes", "routing", "gateway"):
                routes = await self._toolbox.get_routes_report(user_jid=user_jid_str)
                lines = ["🛣️ *Tabel Routing MikroTik*", "━━━━━━━━━━━━━━━━━━"]
                for r in routes[:15]:
                    status = "🟢" if r.get("active") else "⚪"
                    lines.append(f"{status} `{r.get('dst_address')}` ➔ via `{r.get('gateway') or 'local'}`")
                lines.append("━━━━━━━━━━━━━━━━━━")
                await ctx.reply("\n".join(lines))

            elif sub_cmd in ("logs", "log"):
                logs = await self._toolbox.get_logs_report(limit=15, topic=sub_arg, user_jid=user_jid_str)
                await ctx.reply(format_logs_report(logs))

            else:
                await ctx.reply(
                    f"❌ Sub-command `!network {sub_cmd}` tidak dikenali. Ketik `!network help` untuk bantuan."
                )


        except Exception as exc:
            await ctx.reply(format_network_error(exc))
