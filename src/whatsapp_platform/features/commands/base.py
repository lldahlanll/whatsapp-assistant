"""BaseCommandHandler abstract interface."""

from abc import ABC, abstractmethod

from whatsapp_platform.features.commands.context import CommandContext


class BaseCommandHandler(ABC):
    @property
    @abstractmethod
    def command_name(self) -> str:
        """Name of the command e.g. 'ping'."""

    @property
    def description(self) -> str:
        """Description of what the command does."""
        return ""

    @abstractmethod
    async def handle(self, ctx: CommandContext) -> None:
        """Execute command logic."""
