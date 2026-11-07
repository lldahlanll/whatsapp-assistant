"""SchedulerFeature — pengingat & laporan terjadwal yang dikirim bot secara proaktif."""

from __future__ import annotations

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.features.scheduler.service import SchedulerService
from whatsapp_platform.features.scheduler.worker import SchedulerWorker
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class SchedulerFeature(IFeatureModule):
    def __init__(self) -> None:
        self._worker: SchedulerWorker | None = None

    @property
    def name(self) -> str:
        return "scheduler"

    async def initialize(self, container: IContainer) -> None:
        settings = container.resolve(Settings)
        if not settings.scheduler_enabled:
            logger.info("Scheduler disabled via SCHEDULER_ENABLED=false")
            return
        self._worker = SchedulerWorker(
            service=container.resolve(SchedulerService),
            gateway=container.resolve(IMessagingGateway),  # type: ignore[type-abstract]
            poll_seconds=settings.scheduler_poll_seconds,
        )
        self._worker.start()

    async def shutdown(self) -> None:
        if self._worker:
            await self._worker.stop()
