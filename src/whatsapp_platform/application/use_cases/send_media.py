"""SendMediaUseCase."""

import uuid
from datetime import UTC, datetime

import structlog

from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageSent
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import MediaContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus

logger = structlog.get_logger()


class SendMediaUseCase:
    def __init__(
        self,
        gateway: IMessagingGateway,
        message_repo: IMessageRepository,
        event_bus: IEventBus,
    ) -> None:
        self.gateway = gateway
        self.message_repo = message_repo
        self.event_bus = event_bus

    async def execute(
        self, to_jid_str: str, media: MediaContent, caption: str | None = None
    ) -> Message:
        jid = JID.parse(to_jid_str)
        msg_id = await self.gateway.send_media(jid, media, caption=caption)

        message = Message(
            id=msg_id or str(uuid.uuid4()),
            chat_jid=jid,
            sender_jid=JID.parse("me@s.whatsapp.net"),
            content=media,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.SENT,
            timestamp=datetime.now(UTC),
            is_from_me=True,
        )

        await self.message_repo.save(message)
        await self.event_bus.publish(MessageSent(message=message))
        logger.info(
            "Sent media message",
            to=str(jid),
            media_type=media.media_type.value,
            message_id=message.id,
        )
        return message
