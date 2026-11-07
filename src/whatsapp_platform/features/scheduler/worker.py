"""Loop background yang mengirim tugas terjadwal saat jatuh tempo."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
    from whatsapp_platform.features.scheduler.service import SchedulerService

logger = structlog.get_logger()


class SchedulerWorker:
    def __init__(
        self,
        service: SchedulerService,
        gateway: IMessagingGateway,
        poll_seconds: float = 20.0,
    ) -> None:
        self._service = service
        self._gateway = gateway
        self._poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="scheduler-worker")
            logger.info("Scheduler worker started", poll_seconds=self._poll_seconds)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def tick(self) -> int:
        """Satu putaran. WhatsApp belum tersambung -> tunda (jadwal tetap menunggu, tidak hilang)."""
        if not await self._gateway.is_connected():
            return 0
        return await self._service.run_due()

    async def _loop(self) -> None:
        while True:
            try:
                sent = await self.tick()
                if sent:
                    logger.info("Scheduler sent due tasks", count=sent)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Scheduler tick failed", error=str(exc), exc_info=True)
            await asyncio.sleep(self._poll_seconds)
