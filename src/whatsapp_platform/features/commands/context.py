"""CommandContext dataclass provided to command handlers."""

from dataclasses import dataclass

from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.value_objects.bot_command import BotCommand


@dataclass
class CommandContext:
    command: BotCommand
    message: Message
    send_message_uc: SendMessageUseCase
    group_mgmt_uc: GroupManagementUseCase | None = None

    async def reply(self, text: str) -> Message:
        """Helper method to reply to command sender."""
        return await self.send_message_uc.execute(str(self.message.chat_jid), text)
