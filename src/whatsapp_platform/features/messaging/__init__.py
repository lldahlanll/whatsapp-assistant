"""Messaging Feature Module implementing IFeatureModule."""

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.use_cases.receive_message import (
    ReceiveMessageUseCase,
)
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.features.messaging.handlers import InboundMessageHandlers

logger = structlog.get_logger()


class MessagingFeature(IFeatureModule):
    def __init__(self) -> None:
        self.handlers: InboundMessageHandlers | None = None

    @property
    def name(self) -> str:
        return "messaging"

    async def initialize(self, container: IContainer) -> None:
        logger.info("Initializing MessagingFeature module")
        gateway = container.resolve(IMessagingGateway)  # type: ignore[type-abstract]
        message_repo = container.resolve(IMessageRepository)  # type: ignore[type-abstract]

        receive_msg_uc = container.resolve(ReceiveMessageUseCase)

        self.handlers = InboundMessageHandlers(
            message_repo=message_repo,
            receive_message_uc=receive_msg_uc,
        )

        # Only subscribe via gateway — the gateway triggers on_message_received when
        # a real inbound message arrives from WhatsApp. We must NOT also subscribe via
        # event_bus because receive_message_uc.execute() re-publishes MessageReceived
        # to the event_bus, which would trigger on_message_received again → infinite loop.
        gateway.subscribe_event(MessageReceived, self.handlers.on_message_received)

    async def shutdown(self) -> None:
        logger.info("Shutting down MessagingFeature module")
