"""Application Lifecycle runner managing startup and graceful shutdown."""

import asyncio
import signal
import sys
from importlib.metadata import version as _pkg_version

import structlog
import uvicorn

from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.services.feature_registry import FeatureRegistry
from whatsapp_platform.container import Container
from whatsapp_platform.features.ai import AIFeature
from whatsapp_platform.features.commands import CommandsFeature
from whatsapp_platform.features.customer_lookup import CustomerLookupFeature
from whatsapp_platform.features.messaging import MessagingFeature
from whatsapp_platform.features.session import SessionFeature
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.logging.setup import setup_logging
from whatsapp_platform.presentation.api.app import create_api_app

logger = structlog.get_logger()

_APP_VERSION = _pkg_version("whatsapp-platform")


class Application:
    """Top-level application orchestrator.

    Responsibilities:
    - Setup logging and structured context
    - Initialize the DI container (runs Alembic migrations)
    - Register and initialize feature modules
    - Handle OS signals for graceful shutdown
    - Keep the asyncio event loop alive while the platform runs
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.container = Container(self.settings)
        self._running = False
        self._api_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start WhatsApp Platform Application."""
        setup_logging(log_level=self.settings.log_level, app_env=self.settings.app_env)
        logger.info(
            "Starting WhatsApp Platform Application",
            version=_APP_VERSION,
            env=self.settings.app_env,
            session=self.settings.session_name,
        )

        await self.container.initialize()
        feature_registry: FeatureRegistry = self.container.resolve(FeatureRegistry)

        feature_registry.register(SessionFeature())
        feature_registry.register(MessagingFeature())
        feature_registry.register(CommandsFeature())
        feature_registry.register(self.container.resolve(CustomerLookupFeature))
        feature_registry.register(AIFeature())

        await feature_registry.initialize_all(self.container)

        if self.settings.api_enabled:
            self._api_task = asyncio.create_task(self._run_api_server())
            logger.info(
                "🌐 REST API server starting",
                host=self.settings.api_host,
                port=self.settings.api_port,
                docs=f"http://{self.settings.api_host}:{self.settings.api_port}/docs",
            )

        self._running = True
        logger.info("🚀 WhatsApp Platform is running — waiting for events...")

    async def _run_api_server(self) -> None:
        """Run uvicorn ASGI server as an asyncio task alongside Neonize."""
        api_app = create_api_app(self.container)
        config = uvicorn.Config(
            app=api_app,
            host=self.settings.api_host,
            port=self.settings.api_port,
            log_level="warning",  # Suppress uvicorn access logs; structlog handles logging
            access_log=False,
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self) -> None:
        """Graceful shutdown: disconnect gateway, shutdown feature modules."""
        if not self._running:
            return

        logger.info("Stopping WhatsApp Platform Application...")

        if self._api_task and not self._api_task.done():
            self._api_task.cancel()
            try:
                await self._api_task
            except asyncio.CancelledError:
                pass

        try:
            gateway: IMessagingGateway = self.container.resolve(IMessagingGateway)  # type: ignore[type-abstract]
            await gateway.disconnect()
        except Exception as exc:
            logger.warning(
                "Error disconnecting gateway during shutdown", error=str(exc), exc_info=True
            )

        feature_registry: FeatureRegistry = self.container.resolve(FeatureRegistry)
        await feature_registry.shutdown_all()

        await self.container.teardown()

        self._running = False
        logger.info("WhatsApp Platform stopped successfully.")


async def main() -> None:
    app = Application()
    loop = asyncio.get_running_loop()

    _shutdown_task: asyncio.Task[None] | None = None

    def _graceful_shutdown() -> None:
        nonlocal _shutdown_task
        logger.info("Received termination signal — initiating graceful shutdown...")
        _shutdown_task = asyncio.create_task(app.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _graceful_shutdown)
        except NotImplementedError:
            # Windows fallback
            signal.signal(sig, lambda s, f: _graceful_shutdown())

    try:
        await app.start()

        while app._running:
            await asyncio.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        await app.stop()
    except Exception as exc:
        logger.critical(
            "Fatal error in application main loop", error=str(exc), exc_info=True
        )
        await app.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
