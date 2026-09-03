"""GetConversationHistoryUseCase."""

from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.domain.value_objects.jid import JID


class GetConversationHistoryUseCase:
    def __init__(self, message_repo: IMessageRepository) -> None:
        self.message_repo = message_repo

    async def execute(
        self, chat_jid_str: str, limit: int = 50, offset: int = 0
    ) -> list[Message]:
        jid = JID.parse(chat_jid_str)
        return await self.message_repo.get_chat_messages(
            jid, limit=limit, offset=offset
        )
