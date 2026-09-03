"""Inbound message handlers — persist messages and bind correlation context."""

import structlog
import structlog.contextvars

from whatsapp_platform.application.use_cases.receive_message import (
    ReceiveMessageUseCase,
)
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository

logger = structlog.get_logger()


class InboundMessageHandlers:
    """Handles all inbound WhatsApp messages received from the gateway.

    Each message is processed with a ``correlation_id`` bound to the structlog
    context so that every log entry within the same message processing chain
    carries the same ID for traceability.
    """

    def __init__(
        self,
        message_repo: IMessageRepository | None = None,
        receive_message_uc: ReceiveMessageUseCase | None = None,
    ) -> None:
        self.message_repo = message_repo
        self.receive_message_uc = receive_message_uc

    async def on_message_received(self, event: MessageReceived) -> None:
        """Persist inbound message to the database and update conversation aggregate."""
        msg = event.message
        if not msg:
            return

        # Bind correlation_id to all log entries within this call

        structlog.contextvars.bind_contextvars(
            correlation_id=msg.id,
            chat=str(msg.chat_jid),
            sender=str(msg.sender_jid),
        )

        try:
            logger.info(
                "Processing inbound message",
                message_id=msg.id,
                is_from_me=msg.is_from_me,
                media_type=type(msg.content).__name__,
            )

            if self.receive_message_uc:
                await self.receive_message_uc.execute(msg)
            elif self.message_repo:
                await self.message_repo.save(msg)

            logger.debug("Message processed and saved to DB", message_id=msg.id)
        except Exception as exc:
            logger.error(
                "Failed to process inbound message", message_id=msg.id, error=str(exc), exc_info=True
            )
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id", "chat", "sender")
