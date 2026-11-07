"""IScheduleRepository — penyimpanan tugas terjadwal."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from whatsapp_platform.domain.entities.schedule import ScheduledTask


class IScheduleRepository(ABC):
    @abstractmethod
    async def create(self, task: ScheduledTask) -> ScheduledTask:
        """Simpan tugas baru; ``short_id`` diisi otomatis (nomor urut per pemilik)."""

    @abstractmethod
    async def list_active(self, owner_jid: str, chat_jid: str | None = None) -> list[ScheduledTask]: ...

    @abstractmethod
    async def count_active(self, owner_jid: str) -> int: ...

    @abstractmethod
    async def get_by_short_id(self, owner_jid: str, short_id: int) -> ScheduledTask | None: ...

    @abstractmethod
    async def deactivate(self, task_id: str) -> bool: ...

    @abstractmethod
    async def get_due(self, now: datetime, limit: int = 50) -> list[ScheduledTask]:
        """Tugas aktif dengan ``next_run_at <= now``, paling awal dulu."""

    @abstractmethod
    async def save_run_state(self, task: ScheduledTask) -> None:
        """Simpan next_run_at, is_active, last_run_at, run_count, fail_count."""
