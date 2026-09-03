"""Dependency Injection Container — wires all services, use cases, and feature modules."""

import asyncio
import sys
from pathlib import Path
from typing import Any, TypeVar, cast

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.services.event_bus import InMemoryEventBus
from whatsapp_platform.application.services.feature_registry import FeatureRegistry
from whatsapp_platform.application.use_cases.get_conversation import (
    GetConversationHistoryUseCase,
)
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.application.use_cases.receive_message import (
    ReceiveMessageUseCase,
)
from whatsapp_platform.application.use_cases.send_media import SendMediaUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.repositories.contact_repository import IContactRepository
from whatsapp_platform.domain.repositories.conversation_repository import (
    IConversationRepository,
)
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository
from whatsapp_platform.infrastructure.ai.sqlite_store import AISQLiteStore
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.database.base import (
    create_engine_and_session_factory,
)
from whatsapp_platform.infrastructure.database.repositories.contact_repo import (
    SQLAlchemyContactRepository,
)
from whatsapp_platform.infrastructure.database.repositories.conversation_repo import (
    SQLAlchemyConversationRepository,
)
from whatsapp_platform.infrastructure.database.repositories.message_repo import (
    SQLAlchemyMessageRepository,
)
from whatsapp_platform.infrastructure.database.repositories.session_repo import (
    SQLAlchemySessionRepository,
)
from whatsapp_platform.infrastructure.neonize.gateway import NeonizeGateway

T = TypeVar("T")
logger = structlog.get_logger()


class Container(IContainer):
    def __init__(self, settings: Settings | None = None) -> None:
        self._services: dict[type[Any], Any] = {}
        self.settings = settings or Settings()

    async def initialize(self) -> None:
        """Wire all dependencies and register them into the container."""
        logger.info("Initializing DI Container...", app_name=self.settings.app_name)

        self.register(Settings, self.settings)

        await self._run_migrations()
        _engine, session_factory = create_engine_and_session_factory(
            self.settings.database_url
        )

        session_repo = SQLAlchemySessionRepository(session_factory)
        message_repo = SQLAlchemyMessageRepository(session_factory)
        contact_repo = SQLAlchemyContactRepository(session_factory)
        conversation_repo = SQLAlchemyConversationRepository(session_factory)

        self.register(ISessionRepository, session_repo)
        self.register(IMessageRepository, message_repo)
        self.register(IContactRepository, contact_repo)
        self.register(IConversationRepository, conversation_repo)

        event_bus = InMemoryEventBus()
        gateway = NeonizeGateway(session_name=self.settings.session_name)

        self.register(IEventBus, event_bus)
        self.register(IMessagingGateway, gateway)

        send_msg_uc = SendMessageUseCase(gateway, message_repo, event_bus)
        send_media_uc = SendMediaUseCase(gateway, message_repo, event_bus)
        receive_msg_uc = ReceiveMessageUseCase(
            message_repo, conversation_repo
        )
        manage_session_uc = ManageSessionUseCase(gateway, session_repo)
        get_conv_uc = GetConversationHistoryUseCase(message_repo)
        manage_group_uc = GroupManagementUseCase(gateway)

        self.register(SendMessageUseCase, send_msg_uc)
        self.register(SendMediaUseCase, send_media_uc)
        self.register(ReceiveMessageUseCase, receive_msg_uc)
        self.register(ManageSessionUseCase, manage_session_uc)
        self.register(GetConversationHistoryUseCase, get_conv_uc)
        self.register(GroupManagementUseCase, manage_group_uc)

        import httpx

        from whatsapp_platform.application.use_cases.ai_reply import AIReplyUseCase
        from whatsapp_platform.features.ai.config_store import AIChatConfigStore
        from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
        from whatsapp_platform.infrastructure.ai.ai_service import AIService
        from whatsapp_platform.infrastructure.ai.interfaces import ILLMProvider
        from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
        from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy
        from whatsapp_platform.infrastructure.ai.providers.gemini import GeminiProvider
        from whatsapp_platform.infrastructure.ai.providers.groq import GroqProvider
        from whatsapp_platform.infrastructure.ai.providers.openrouter import OpenRouterProvider

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.ai_http_timeout_seconds)
        )

        ai_sqlite_store = AISQLiteStore(db_path=self.settings.ai_database_path)
        await ai_sqlite_store.initialize()

        providers_map: dict[str, tuple[ILLMProvider, KeyPool]] = {}

        if self.settings.gemini_api_keys:
            gemini_adapter = GeminiProvider(
                self._http_client, cooldown_default=self.settings.ai_cooldown_default_seconds
            )
            gemini_pool = KeyPool(
                cast(list[str], self.settings.gemini_api_keys),
                default_cooldown_seconds=self.settings.ai_cooldown_default_seconds,
            )
            providers_map["gemini"] = (gemini_adapter, gemini_pool)

        if self.settings.groq_api_keys:
            groq_adapter = GroqProvider(
                self._http_client, cooldown_default=self.settings.ai_cooldown_default_seconds
            )
            groq_pool = KeyPool(
                cast(list[str], self.settings.groq_api_keys),
                default_cooldown_seconds=self.settings.ai_cooldown_default_seconds,
            )
            providers_map["groq"] = (groq_adapter, groq_pool)

        if self.settings.openrouter_api_keys:
            openrouter_adapter = OpenRouterProvider(
                self._http_client, cooldown_default=self.settings.ai_cooldown_default_seconds
            )
            openrouter_pool = KeyPool(
                cast(list[str], self.settings.openrouter_api_keys),
                default_cooldown_seconds=self.settings.ai_cooldown_default_seconds,
            )
            providers_map["openrouter"] = (openrouter_adapter, openrouter_pool)

        strategy = FixedPriorityStrategy(["gemini", "groq", "openrouter"])
        ai_service = AIService(
            providers=providers_map,
            strategy=strategy,
            db_store=ai_sqlite_store,
            max_context_messages=self.settings.ai_context_window_messages,
        )
        await ai_service.initialize()

        from whatsapp_platform.features.network.permission import NetworkPermissionChecker
        from whatsapp_platform.features.network.rate_guard import NetworkRateGuard
        from whatsapp_platform.infrastructure.mikrotik.cache import MikroTikCache
        from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient
        from whatsapp_platform.infrastructure.mikrotik.tool_executor import MikroTikToolExecutor
        from whatsapp_platform.infrastructure.mikrotik.toolbox import NetworkToolbox

        mikrotik_client = MikroTikRestClient(settings=self.settings, http_client=self._http_client)
        mikrotik_cache = MikroTikCache()
        network_toolbox = NetworkToolbox(
            client=mikrotik_client,
            cache=mikrotik_cache,
            settings=self.settings,
        )
        network_perm_checker = NetworkPermissionChecker(settings=self.settings)
        network_rate_guard = NetworkRateGuard()
        mikrotik_tool_executor = MikroTikToolExecutor(
            toolbox=network_toolbox,
            permission_checker=network_perm_checker,
        )

        self.register(MikroTikRestClient, mikrotik_client)
        self.register(MikroTikCache, mikrotik_cache)
        self.register(NetworkToolbox, network_toolbox)
        self.register(NetworkPermissionChecker, network_perm_checker)
        self.register(NetworkRateGuard, network_rate_guard)
        self.register(MikroTikToolExecutor, mikrotik_tool_executor)

        # Finance feature wiring
        from whatsapp_platform.features.finance.service import FinanceService
        from whatsapp_platform.infrastructure.ai.composite_executor import CompositeToolExecutor
        from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
            SQLAlchemyFinanceRepository,
        )
        from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor

        finance_repo = SQLAlchemyFinanceRepository(session_factory)
        finance_service = FinanceService(repo=finance_repo)
        finance_tool_executor = FinanceToolExecutor(finance_service=finance_service)

        self.register(SQLAlchemyFinanceRepository, finance_repo)
        self.register(FinanceService, finance_service)
        self.register(FinanceToolExecutor, finance_tool_executor)

        # Composite executor combining all tool domains
        composite_executor = CompositeToolExecutor()
        composite_executor.register("mikrotik", mikrotik_tool_executor)
        composite_executor.register("finance", finance_tool_executor)
        self.register(CompositeToolExecutor, composite_executor)

        ai_reply_uc = AIReplyUseCase(
            ai_service=ai_service,
            get_conv_uc=get_conv_uc,
            tool_executor=composite_executor,
            context_window_messages=self.settings.ai_context_window_messages,
            max_context_chars=self.settings.ai_max_context_chars,
        )

        ai_config_store = AIChatConfigStore(db_store=ai_sqlite_store)
        await ai_config_store.initialize()

        ai_rate_guard = PerChatRateGuard(
            max_requests=self.settings.ai_rate_limit_max_requests,
            window_seconds=self.settings.ai_rate_limit_window_seconds,
        )

        self.register(AISQLiteStore, ai_sqlite_store)
        self.register(AIService, ai_service)
        self.register(AIReplyUseCase, ai_reply_uc)
        self.register(AIChatConfigStore, ai_config_store)
        self.register(PerChatRateGuard, ai_rate_guard)

        from whatsapp_platform.features.customer_lookup import CustomerLookupFeature
        from whatsapp_platform.features.customer_lookup.handler import CustomerLookupHandler
        from whatsapp_platform.features.customer_lookup.rate_guard import PerSenderRateGuard
        from whatsapp_platform.infrastructure.customer_lookup import (
            CustomerLookupRepository,
        )

        customer_lookup_repo = CustomerLookupRepository(settings=self.settings)
        customer_lookup_guard = PerSenderRateGuard()
        customer_lookup_handler = CustomerLookupHandler(
            repository=customer_lookup_repo,
            send_msg_uc=send_msg_uc,
            rate_guard=customer_lookup_guard,
            settings=self.settings,
        )
        customer_lookup_feature = CustomerLookupFeature(handler=customer_lookup_handler)

        self.register(CustomerLookupRepository, customer_lookup_repo)
        self.register(PerSenderRateGuard, customer_lookup_guard)
        self.register(CustomerLookupHandler, customer_lookup_handler)
        self.register(CustomerLookupFeature, customer_lookup_feature)

        feature_registry = FeatureRegistry()
        self.register(FeatureRegistry, feature_registry)

    async def teardown(self) -> None:
        """Cleanup resources allocated by container (HTTP client, SQLite, MySQL pool, MikroTik)."""
        from whatsapp_platform.infrastructure.customer_lookup import close_pool
        from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient

        try:
            await close_pool()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing MySQL pool during teardown", error=str(exc))

        if MikroTikRestClient in self._services:
            mikrotik_client: MikroTikRestClient = self.resolve(MikroTikRestClient)
            await mikrotik_client.aclose()

        if AISQLiteStore in self._services:
            ai_sqlite_store: AISQLiteStore = self.resolve(AISQLiteStore)
            await ai_sqlite_store.close()

        if hasattr(self, "_http_client") and self._http_client:
            await self._http_client.aclose()
            logger.info("Closed container shared HTTP client")




    def register(self, interface: Any, instance: Any) -> None:
        self._services[interface] = instance

    def resolve(self, interface: type[T] | Any) -> T:
        if interface not in self._services:
            raise KeyError(
                f"Service '{getattr(interface, '__name__', str(interface))}' is not registered in DI Container"
            )
        return self._services[interface]  # type: ignore[no-any-return]

    async def _run_migrations(self) -> None:
        """Run Alembic migrations asynchronously via subprocess.

        Executes `alembic upgrade head` in the project root directory.
        This ensures the database schema is always up-to-date on startup.
        """
        project_root = Path(__file__).resolve().parents[2]
        logger.info("Running Alembic migrations...", cwd=str(project_root))
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "alembic",
                "upgrade",
                "head",
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error("Alembic migration failed", error=error_msg)
                raise RuntimeError(f"Alembic migration failed: {error_msg}")
            logger.info("Alembic migrations completed", output=stdout.decode().strip())
        except FileNotFoundError as exc:
            raise RuntimeError(
                "'alembic' command not found. Ensure it is installed in the virtual environment."
            ) from exc
