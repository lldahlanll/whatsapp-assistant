"""HelpHandler for !help command."""

from collections.abc import Callable

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext


class HelpHandler(BaseCommandHandler):
    def __init__(self, get_commands_fn: Callable[[], list[BaseCommandHandler]]) -> None:
        self.get_commands_fn = get_commands_fn

    @property
    def command_name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Display list of available commands"

    async def handle(self, ctx: CommandContext) -> None:
        commands = self.get_commands_fn()
        lines = ["🤖 *Available Commands:*"]
        prefix = ctx.command.prefix

        for cmd in commands:
            desc = cmd.description or "No description provided."
            lines.append(f"• `{prefix}{cmd.command_name}`: {desc}")

        help_text = "\n".join(lines)
        await ctx.reply(help_text)
