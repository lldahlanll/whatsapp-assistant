"""SQLAlchemy implementation of IScheduleRepository.

Waktu disimpan sebagai UTC naive (konvensi DB proyek) dan dikembalikan sebagai UTC aware.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from whatsapp_platform.domain.entities.schedule import Recurrence, ScheduledTask, TaskKind
from whatsapp_platform.domain.repositories.schedule_repository import IScheduleRepository
from whatsapp_platform.infrastructure.database.models import ScheduledTaskModel

_CREATE_RETRIES = 3


def _to_db(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _from_db(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _task_from_model(m: ScheduledTaskModel) -> ScheduledTask:
    return ScheduledTask(
        id=m.id,
        owner_jid=m.owner_jid,
        chat_jid=m.chat_jid,
        kind=TaskKind(m.kind),
        message=m.message,
        recurrence=Recurrence(m.recurrence),
        next_run_at=_from_db(m.next_run_at),  # type: ignore[arg-type]
        anchor_day=m.anchor_day,
        is_active=m.is_active,
        created_at=_from_db(m.created_at),  # type: ignore[arg-type]
        last_run_at=_from_db(m.last_run_at),
        run_count=m.run_count,
        fail_count=m.fail_count,
        short_id=m.short_id,
    )


class SQLAlchemyScheduleRepository(IScheduleRepository):
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def _session(self) -> AsyncSession:
        return self._session_factory()

    async def create(self, task: ScheduledTask) -> ScheduledTask:
        # short_id = max+1 per pemilik; dua pembuatan bersamaan bisa bentrok di unique index -> ulangi.
        for attempt in range(_CREATE_RETRIES):
            async with self._session() as session:
                current_max = await session.scalar(
                    select(func.max(ScheduledTaskModel.short_id)).where(
                        ScheduledTaskModel.owner_jid == task.owner_jid
                    )
                )
                model = ScheduledTaskModel(
                    id=task.id,
                    owner_jid=task.owner_jid,
                    chat_jid=task.chat_jid,
                    short_id=int(current_max or 0) + 1,
                    kind=task.kind.value,
                    message=task.message,
                    recurrence=task.recurrence.value,
                    next_run_at=_to_db(task.next_run_at),
                    anchor_day=task.anchor_day,
                    is_active=task.is_active,
                    last_run_at=_to_db(task.last_run_at),
                    run_count=task.run_count,
                    fail_count=task.fail_count,
                    created_at=_to_db(task.created_at),
                )
                session.add(model)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    if attempt == _CREATE_RETRIES - 1:
                        raise
                    continue
                await session.refresh(model)
                return _task_from_model(model)
        raise RuntimeError("unreachable")

    async def list_active(self, owner_jid: str, chat_jid: str | None = None) -> list[ScheduledTask]:
        async with self._session() as session:
            stmt = select(ScheduledTaskModel).where(
                ScheduledTaskModel.owner_jid == owner_jid,
                ScheduledTaskModel.is_active.is_(True),
            )
            if chat_jid is not None:
                stmt = stmt.where(ScheduledTaskModel.chat_jid == chat_jid)
            result = await session.execute(stmt.order_by(ScheduledTaskModel.next_run_at))
            return [_task_from_model(m) for m in result.scalars().all()]

    async def count_active(self, owner_jid: str) -> int:
        async with self._session() as session:
            count = await session.scalar(
                select(func.count()).select_from(ScheduledTaskModel).where(
                    ScheduledTaskModel.owner_jid == owner_jid,
                    ScheduledTaskModel.is_active.is_(True),
                )
            )
            return int(count or 0)

    async def get_by_short_id(self, owner_jid: str, short_id: int) -> ScheduledTask | None:
        async with self._session() as session:
            m = (
                await session.execute(
                    select(ScheduledTaskModel).where(
                        ScheduledTaskModel.owner_jid == owner_jid,
                        ScheduledTaskModel.short_id == short_id,
                    )
                )
            ).scalar_one_or_none()
            return _task_from_model(m) if m else None

    async def deactivate(self, task_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.is_active.is_(True))
                .values(is_active=False)
            )
            await session.commit()
            return bool(result.rowcount)  # type: ignore[attr-defined]

    async def get_due(self, now: datetime, limit: int = 50) -> list[ScheduledTask]:
        async with self._session() as session:
            result = await session.execute(
                select(ScheduledTaskModel)
                .where(
                    ScheduledTaskModel.is_active.is_(True),
                    ScheduledTaskModel.next_run_at <= _to_db(now),
                )
                .order_by(ScheduledTaskModel.next_run_at)
                .limit(limit)
            )
            return [_task_from_model(m) for m in result.scalars().all()]

    async def save_run_state(self, task: ScheduledTask) -> None:
        async with self._session() as session:
            await session.execute(
                update(ScheduledTaskModel)
                .where(ScheduledTaskModel.id == task.id)
                .values(
                    next_run_at=_to_db(task.next_run_at),
                    is_active=task.is_active,
                    last_run_at=_to_db(task.last_run_at),
                    run_count=task.run_count,
                    fail_count=task.fail_count,
                )
            )
            await session.commit()
