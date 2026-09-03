"""Session Feature Module — manages session lifecycle events and reconnection.

Responsibilities:
- Wire the IEventBus to the NeonizeGateway so all domain events flow through
  the application event bus.
- Display QR code when WhatsApp requests pairing.
- Persist session state changes (CONNECTED / DISCONNECTED) to the database.
- Trigger auto-reconnect with exponential backoff when disconnected.
- Start the session (connect / pair by code) on initialization.
"""

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.domain.events.session_events import (
    QRCodeGenerated,
    SessionConnected,
    SessionDisconnected,
)
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository
from whatsapp_platform.features.session.manager import SessionManager
from whatsapp_platform.features.session.qr_handler import QRDisplayHandler
from whatsapp_platform.features.session.reconnect import ExponentialBackoffReconnector
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class SessionFeature(IFeatureModule):
    """Feature module that owns the entire session lifecycle."""

    def __init__(self) -> None:
        self.reconnector: ExponentialBackoffReconnector | None = None
        self.manager: SessionManager | None = None
        self._session_repo: ISessionRepository | None = None
        self._settings: Settings | None = None

    @property
    def name(self) -> str:
        return "session"

    async def initialize(self, container: IContainer) -> None:
        logger.info("Initializing SessionFeature module")

        event_bus: IEventBus = container.resolve(IEventBus)  # type: ignore[type-abstract]
        gateway: IMessagingGateway = container.resolve(IMessagingGateway)  # type: ignore[type-abstract]
        session_repo: ISessionRepository = container.resolve(ISessionRepository)  # type: ignore[type-abstract]

        settings: Settings = container.resolve(Settings)
        manage_session_uc: ManageSessionUseCase = container.resolve(
            ManageSessionUseCase
        )

        self._session_repo = session_repo
        self._settings = settings

        # ----------------------------------------------------------------
        # 1. Bridge: wire EventBus into the gateway so that all Neonize
        #    events are automatically forwarded to the application EventBus.
        # ----------------------------------------------------------------
        gateway.set_event_bus(event_bus)
        logger.debug("Gateway EventBus bridge established")

        # ----------------------------------------------------------------
        # 2. QR Code display — render QR on terminal whenever WA sends one.
        #    WA re-sends QREv every ~60 seconds if not scanned, so this
        #    handler naturally handles QR refresh.
        # ----------------------------------------------------------------
        event_bus.subscribe(QRCodeGenerated, QRDisplayHandler.on_qr_generated)
        logger.debug("Subscribed QRDisplayHandler to QRCodeGenerated")

        # ----------------------------------------------------------------
        # 3. Session state persistence — update DB when WA confirms connect.
        # ----------------------------------------------------------------
        event_bus.subscribe(SessionConnected, self._on_session_connected)
        logger.debug("Subscribed _on_session_connected to SessionConnected")

        # ----------------------------------------------------------------
        # 4. Auto-reconnect with exponential backoff on disconnect.
        # ----------------------------------------------------------------
        self.reconnector = ExponentialBackoffReconnector(gateway, session_repo)
        event_bus.subscribe(SessionDisconnected, self.reconnector.on_disconnected)
        logger.debug("Subscribed ExponentialBackoffReconnector to SessionDisconnected")

        # ----------------------------------------------------------------
        # 5. Start session — connect via QR or pairing code.
        # ----------------------------------------------------------------
        self.manager = SessionManager(manage_session_uc, settings)
        await self.manager.start()
        logger.info(
            "SessionFeature initialization complete", method=settings.pairing_method
        )

    async def _on_session_connected(self, event: SessionConnected) -> None:
        """Persist CONNECTED status and phone number to DB when WA confirms connection."""
        if self._session_repo is None:
            return

        session = await self._session_repo.get_by_id(event.session_id)
        if not session:
            logger.warning(
                "SessionConnected received but no session found in DB",
                session_id=event.session_id,
            )
            return

        session.connect()
        if event.phone_number:
            session.phone_number = event.phone_number

        await self._session_repo.save(session)
        logger.info(
            "✅ Session CONNECTED — state persisted to DB",
            session_id=event.session_id,
            phone_number=event.phone_number or "unknown",
        )

    async def shutdown(self) -> None:
        logger.info("Shutting down SessionFeature module")
