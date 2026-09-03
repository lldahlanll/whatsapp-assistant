"""PingHandler for !ping command."""

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext


class PingHandler(BaseCommandHandler):
    @property
    def command_name(self) -> str:
        return "ping"

    @property
    def description(self) -> str:
        return "Check bot responsiveness (replies with pong 🏓)"

    async def handle(self, ctx: CommandContext) -> None:
        await ctx.reply("pong 🏓")
