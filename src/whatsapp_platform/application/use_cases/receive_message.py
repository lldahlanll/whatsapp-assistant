"""ReceiveMessageUseCase — processes incoming messages and updates conversation aggregate."""

from datetime import UTC, datetime

import structlog

from whatsapp_platform.domain.entities.conversation import Conversation
from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.repositories.conversation_repository import (
    IConversationRepository,
)
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository

logger = structlog.get_logger()


class ReceiveMessageUseCase:
    """Use case for processing incoming WhatsApp messages.

    Persists the Message entity and updates the Conversation aggregate root
    (last_message, unread_count, updated_at).
    """

    def __init__(
        self,
        message_repo: IMessageRepository,
        conversation_repo: IConversationRepository,
    ) -> None:
        self.message_repo = message_repo
        self.conversation_repo = conversation_repo

    async def execute(self, message: Message) -> Message:
        """Process an incoming message.

        Args:
            message: The Message domain entity to process.

        Returns:
            The saved Message entity.
        """
        # 1. Save message entity to database (atomic upsert — safe for concurrent calls)
        await self.message_repo.save(message)
        logger.debug(
            "Message persisted", message_id=message.id, chat=str(message.chat_jid)
        )

        # 2. Retrieve or create Conversation aggregate
        conversation = await self.conversation_repo.get_by_jid(message.chat_jid)
        if not conversation:
            conversation = Conversation(
                chat_jid=message.chat_jid,
                unread_count=0,
                last_message=None,
                messages=[],
                updated_at=message.timestamp or datetime.now(UTC),
            )

        # 3. Update Conversation state with the new message
        conversation.add_message(message)
        await self.conversation_repo.save(conversation)
        logger.debug(
            "Conversation updated",
            chat=str(message.chat_jid),
            unread_count=conversation.unread_count,
        )

        return message
