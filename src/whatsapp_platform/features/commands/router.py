"""CommandRouter for dispatching registered command handlers with Middleware support."""

from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.events.command_events import (
    CommandExecuted,
    UnknownCommandReceived,
)
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.bot_command import BotCommand
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()

# Middleware signature: async function receiving ctx, returning bool (True to continue, False to abort)
CommandMiddleware = Callable[[CommandContext], Coroutine[Any, Any, bool]]


class CommandRouter:
    """Extensible command router supporting command registration and middleware pipeline."""

    def __init__(
        self,
        send_msg_uc: SendMessageUseCase,
        event_bus: IEventBus,
        prefix: str = "!",
        group_mgmt_uc: GroupManagementUseCase | None = None,
    ) -> None:
        self.send_msg_uc = send_msg_uc
        self.event_bus = event_bus
        self.prefix = prefix
        self.group_mgmt_uc = group_mgmt_uc
        self._handlers: dict[str, BaseCommandHandler] = {}
        self._middlewares: list[CommandMiddleware] = []

    def register(self, handler: BaseCommandHandler) -> None:
        """Register a command handler."""
        name = handler.command_name.lower()
        if name in self._handlers:
            logger.warning("Overwriting registered command handler", command=name)
        self._handlers[name] = handler
        logger.info("Registered command handler", command=name)

    def use_middleware(self, middleware: CommandMiddleware) -> None:
        """Add a middleware function to the command execution pipeline."""
        self._middlewares.append(middleware)
        logger.debug("Registered command middleware", middleware=middleware.__name__)

    @property
    def registered_commands(self) -> list[BaseCommandHandler]:
        return list(self._handlers.values())

    async def on_message_received(self, event: MessageReceived) -> None:
        """Process inbound MessageReceived domain event and route to matching command."""
        msg = event.message
        if not msg:
            return

        if msg.is_from_me:
            return

        if not isinstance(msg.content, TextContent):
            return

        text = msg.content.text.strip()
        command = BotCommand.parse(text, prefix=self.prefix)
        if not command:
            return

        logger.info(
            "Command detected", command_name=command.name, chat=str(msg.chat_jid)
        )

        handler = self._handlers.get(command.name)
        if not handler:
            await self.event_bus.publish(
                UnknownCommandReceived(
                    raw_command=command.name,
                    chat_jid=msg.chat_jid,
                    sender_jid=msg.sender_jid,
                )
            )
            logger.info("Unknown command received", command_name=command.name)
            return

        ctx = CommandContext(
            command=command,
            message=msg,
            send_message_uc=self.send_msg_uc,
            group_mgmt_uc=self.group_mgmt_uc,
        )

        # Execute middleware chain
        for mw in self._middlewares:
            try:
                should_continue = await mw(ctx)
                if not should_continue:
                    logger.info(
                        "Command execution halted by middleware",
                        command=command.name,
                        middleware=mw.__name__,
                    )
                    return
            except Exception as exc:
                logger.error(
                    "Middleware execution error",
                    middleware=mw.__name__,
                    command=command.name,
                    error=str(exc),
                    exc_info=True,
                )
                return

        # Execute handler
        try:
            await handler.handle(ctx)
            await self.event_bus.publish(
                CommandExecuted(
                    command=command,
                    chat_jid=msg.chat_jid,
                    sender_jid=msg.sender_jid,
                    handler_name=handler.__class__.__name__,
                )
            )
        except Exception as exc:
            logger.error(
                "Error executing command handler", command=command.name, error=str(exc), exc_info=True
            )
            await ctx.reply(f"❌ Error executing command '{command.name}': {exc}")
