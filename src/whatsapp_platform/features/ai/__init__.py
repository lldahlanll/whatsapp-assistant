"""AIFeature Module implementing IFeatureModule."""

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.ai.handler import AIMessageHandler
from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class AIFeature(IFeatureModule):
    """Feature module managing AI auto-reply functionality."""

    def __init__(self) -> None:
        self.handler: AIMessageHandler | None = None

    @property
    def name(self) -> str:
        return "ai"

    async def initialize(self, container: IContainer) -> None:
        logger.info("Initializing AIFeature module")
        gateway = container.resolve(IMessagingGateway)  # type: ignore[type-abstract]
        ai_reply_uc = container.resolve(AIReplyUseCase)
        send_msg_uc = container.resolve(SendMessageUseCase)
        config_store = container.resolve(AIChatConfigStore)
        rate_guard = container.resolve(PerChatRateGuard)
        settings = container.resolve(Settings)
        message_repo = container.resolve(IMessageRepository)  # type: ignore[type-abstract]

        self.handler = AIMessageHandler(
            ai_reply_uc=ai_reply_uc,
            send_msg_uc=send_msg_uc,
            config_store=config_store,
            rate_guard=rate_guard,
            settings=settings,
            message_repo=message_repo,
            gateway=gateway,
        )

        gateway.subscribe_event(MessageReceived, self.handler.on_message_received)

    async def shutdown(self) -> None:
        logger.info("Shutting down AIFeature module")
