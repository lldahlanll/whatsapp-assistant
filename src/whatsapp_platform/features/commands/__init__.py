"""Commands Feature Module implementing IFeatureModule."""

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.features.commands.handlers.add import AddHandler
from whatsapp_platform.features.commands.handlers.ai_config import AIChatCommandHandler
from whatsapp_platform.features.commands.handlers.demote import DemoteHandler
from whatsapp_platform.features.commands.handlers.finance import FinanceCommandHandler
from whatsapp_platform.features.commands.handlers.group_info import GroupInfoHandler
from whatsapp_platform.features.commands.handlers.help import HelpHandler
from whatsapp_platform.features.commands.handlers.invite_link import InviteLinkHandler
from whatsapp_platform.features.commands.handlers.kick import KickHandler
from whatsapp_platform.features.commands.handlers.ping import PingHandler
from whatsapp_platform.features.commands.handlers.promote import PromoteHandler
from whatsapp_platform.features.commands.handlers.set_name import SetNameHandler
from whatsapp_platform.features.commands.handlers.status import StatusCommandHandler
from whatsapp_platform.features.commands.router import CommandRouter
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class CommandsFeature(IFeatureModule):
    def __init__(self) -> None:
        self.router: CommandRouter | None = None

    @property
    def name(self) -> str:
        return "commands"

    async def initialize(self, container: IContainer) -> None:
        logger.info("Initializing CommandsFeature module")
        event_bus = container.resolve(IEventBus)  # type: ignore[type-abstract]
        gateway = container.resolve(IMessagingGateway)  # type: ignore[type-abstract]

        send_msg_uc = container.resolve(SendMessageUseCase)
        group_mgmt_uc = container.resolve(GroupManagementUseCase)
        settings = container.resolve(Settings)
        config_store = container.resolve(AIChatConfigStore)
        ai_service = container.resolve(AIService)

        router = CommandRouter(
            send_msg_uc,
            event_bus,
            prefix=settings.command_prefix,
            group_mgmt_uc=group_mgmt_uc,
        )
        self.router = router

        # Register built-in command handlers
        router.register(PingHandler())
        router.register(HelpHandler(lambda: router.registered_commands))
        router.register(StatusCommandHandler())
        router.register(GroupInfoHandler())
        router.register(InviteLinkHandler())
        router.register(KickHandler())
        router.register(AddHandler())
        router.register(PromoteHandler())
        router.register(DemoteHandler())
        router.register(SetNameHandler())
        router.register(AIChatCommandHandler(config_store, ai_service))

        from whatsapp_platform.features.commands.handlers.network import NetworkCommandHandler
        from whatsapp_platform.features.network.permission import NetworkPermissionChecker
        from whatsapp_platform.features.network.rate_guard import NetworkRateGuard
        from whatsapp_platform.infrastructure.mikrotik.toolbox import NetworkToolbox

        network_toolbox = container.resolve(NetworkToolbox)
        network_perm_checker = container.resolve(NetworkPermissionChecker)
        network_rate_guard = container.resolve(NetworkRateGuard)

        router.register(NetworkCommandHandler(network_toolbox, network_perm_checker, network_rate_guard))

        from whatsapp_platform.features.finance.service import FinanceService

        finance_service = container.resolve(FinanceService)
        router.register(FinanceCommandHandler(finance_service))

        gateway.subscribe_event(MessageReceived, router.on_message_received)

    async def shutdown(self) -> None:
        logger.info("Shutting down CommandsFeature module")

