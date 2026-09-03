"""CustomerLookupFeature Module implementing IFeatureModule."""

from __future__ import annotations

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.features.customer_lookup.handler import CustomerLookupHandler
from whatsapp_platform.features.customer_lookup.rate_guard import PerSenderRateGuard
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.customer_lookup.repository import CustomerLookupRepository

logger = structlog.get_logger()


class CustomerLookupFeature(IFeatureModule):
    """Feature module managing WhatsApp customer lookup functionality."""

    def __init__(self, handler: CustomerLookupHandler | None = None) -> None:
        self.handler: CustomerLookupHandler | None = handler

    @property
    def name(self) -> str:
        return "customer_lookup"

    async def initialize(self, container: IContainer) -> None:
        logger.info("Initializing CustomerLookupFeature module")
        gateway = container.resolve(IMessagingGateway)  # type: ignore[type-abstract]

        if self.handler is None:
            repository = container.resolve(CustomerLookupRepository)
            send_msg_uc = container.resolve(SendMessageUseCase)
            rate_guard = container.resolve(PerSenderRateGuard)
            settings = container.resolve(Settings)

            self.handler = CustomerLookupHandler(
                repository=repository,
                send_msg_uc=send_msg_uc,
                rate_guard=rate_guard,
                settings=settings,
            )

        gateway.subscribe_event(MessageReceived, self.handler.on_message_received)

    async def shutdown(self) -> None:
        logger.info("Shutting down CustomerLookupFeature module")
