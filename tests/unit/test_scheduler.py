"""Scheduler: pengingat & laporan terjadwal (recurrence, service+DB, worker, tool AI, command, routing)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.schedule import Recurrence, TaskKind
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.handlers.reminder import ReminderCommandHandler, _parse_create
from whatsapp_platform.features.scheduler.recurrence import advance_past, next_occurrence
from whatsapp_platform.features.scheduler.service import (
    MAX_ACTIVE_TASKS_PER_USER,
    MAX_SEND_FAILURES,
    SchedulerError,
    SchedulerService,
    TaskNotFoundError,
    resolve_first_run,
)
from whatsapp_platform.features.scheduler.worker import SchedulerWorker
from whatsapp_platform.infrastructure.ai.context_policy import ContextPolicyManager
from whatsapp_platform.infrastructure.ai.reminder_executor import ReminderToolExecutor
from whatsapp_platform.infrastructure.ai.reminder_tools import wants_reminder_tools
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.schedule_repo import (
    SQLAlchemyScheduleRepository,
)
from whatsapp_platform.shared.utils.timezone import LOCAL_TZ, to_local

OWNER = "628111@s.whatsapp.net"
OTHER = "628222@s.whatsapp.net"
GROUP = "12345@g.us"


def wib(*args: int) -> datetime:
    return datetime(*args, tzinfo=LOCAL_TZ).astimezone(UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# ── Recurrence ────────────────────────────────────────────────────────────────


def test_next_occurrence_rules():
    fri = wib(2026, 11, 6, 8, 0)  # Jumat
    assert next_occurrence(fri, Recurrence.ONCE) is None
    assert next_occurrence(fri, Recurrence.DAILY) == wib(2026, 11, 7, 8, 0)
    assert next_occurrence(fri, Recurrence.WEEKDAYS) == wib(2026, 11, 9, 8, 0)  # lompat ke Senin
    assert next_occurrence(fri, Recurrence.WEEKLY) == wib(2026, 11, 13, 8, 0)


def test_monthly_keeps_anchor_day_after_short_month():
    jan31 = wib(2027, 1, 31, 9, 0)
    feb = next_occurrence(jan31, Recurrence.MONTHLY, anchor_day=31)
    assert feb == wib(2027, 2, 28, 9, 0)
    assert next_occurrence(feb, Recurrence.MONTHLY, anchor_day=31) == wib(2027, 3, 31, 9, 0)
    dec = wib(2026, 12, 5, 9, 0)
    assert next_occurrence(dec, Recurrence.MONTHLY, anchor_day=5) == wib(2027, 1, 5, 9, 0)


def test_advance_past_skips_missed_occurrences():
    start = wib(2026, 11, 1, 8, 0)
    now = wib(2026, 11, 6, 10, 0)
    assert advance_past(start, now, Recurrence.DAILY) == wib(2026, 11, 7, 8, 0)


# ── resolve_first_run ─────────────────────────────────────────────────────────

NOW = wib(2026, 11, 6, 10, 0)  # Jumat 10:00 WIB


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"delay_minutes": 30}, wib(2026, 11, 6, 10, 30)),
        ({"time_of_day": "15:00"}, wib(2026, 11, 6, 15, 0)),
        ({"time_of_day": "08:00"}, wib(2026, 11, 7, 8, 0)),  # sudah lewat -> besok
        ({"weekday": "senin", "time_of_day": "07:00"}, wib(2026, 11, 9, 7, 0)),
        ({"weekday": "jumat", "time_of_day": "09:00"}, wib(2026, 11, 13, 9, 0)),  # hari ini lewat -> minggu depan
        ({"day_of_month": 5, "time_of_day": "09:00"}, wib(2026, 12, 5, 9, 0)),
        ({"day_of_month": 31}, wib(2026, 11, 30, 8, 0)),  # November cuma 30 hari, jam default 08:00
    ],
)
def test_resolve_first_run(kwargs, expected):
    assert resolve_first_run(NOW, **kwargs) == expected


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"time_of_day": "25:00"}, {"weekday": "funday"}, {"day_of_month": 40}, {"delay_minutes": 0}],
)
def test_resolve_first_run_rejects_bad_input(kwargs):
    with pytest.raises(SchedulerError):
        resolve_first_run(NOW, **kwargs)


# ── Service + SQLite ──────────────────────────────────────────────────────────


@pytest.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SQLAlchemyScheduleRepository(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    await engine.dispose()


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def sender():
    return AsyncMock()


@pytest.fixture
def svc(repo, clock, sender):
    return SchedulerService(
        repo, send=sender, build_finance_report=AsyncMock(return_value="LAPORAN"), clock=clock
    )


async def test_create_assigns_short_ids_per_owner(svc):
    a = await svc.create_task(OWNER, OWNER, message="Minum obat", time_of_day="12:00")
    b = await svc.create_task(OWNER, OWNER, message="Telepon ibu", delay_minutes=5)
    c = await svc.create_task(OTHER, OTHER, message="Lain", delay_minutes=5)
    assert (a.short_id, b.short_id, c.short_id) == (1, 2, 1)


async def test_create_validation(svc):
    with pytest.raises(SchedulerError, match="Isi pengingat"):
        await svc.create_task(OWNER, OWNER, message="  ", delay_minutes=5)
    with pytest.raises(SchedulerError, match="sudah lewat"):
        await svc.create_task(OWNER, OWNER, message="x", run_at=NOW - timedelta(hours=1))
    with pytest.raises(SchedulerError, match="1 tahun"):
        await svc.create_task(OWNER, OWNER, message="x", run_at=NOW + timedelta(days=400))
    with pytest.raises(SchedulerError, match="chat pribadi"):
        await svc.create_task(OWNER, GROUP, kind="finance_report", is_group=True)
    with pytest.raises(SchedulerError, match="tidak dikenal"):
        await svc.create_task(OWNER, OWNER, message="x", delay_minutes=5, recurrence="hourly")


async def test_recurring_with_past_run_at_rolls_forward(svc):
    task = await svc.create_task(
        OWNER, OWNER, message="Absen", recurrence="daily", run_at=wib(2026, 11, 6, 8, 0)
    )
    assert task.next_run_at == wib(2026, 11, 7, 8, 0)


async def test_weekdays_first_run_skips_weekend(svc):
    task = await svc.create_task(
        OWNER, OWNER, message="Absen", recurrence="weekdays", run_at=wib(2026, 11, 7, 7, 0)  # Sabtu
    )
    assert task.next_run_at == wib(2026, 11, 9, 7, 0)


async def test_active_task_limit(svc):
    for i in range(MAX_ACTIVE_TASKS_PER_USER):
        await svc.create_task(OWNER, OWNER, message=f"t{i}", delay_minutes=10 + i)
    with pytest.raises(SchedulerError, match="Batas"):
        await svc.create_task(OWNER, OWNER, message="lagi", delay_minutes=5)


async def test_group_privacy_for_list_and_cancel(svc):
    private = await svc.create_task(OWNER, OWNER, message="Rahasia", delay_minutes=5)
    group = await svc.create_task(OWNER, GROUP, message="Rapat", delay_minutes=5, is_group=True)

    in_group = await svc.list_tasks(OWNER, GROUP, is_group=True)
    assert [t.short_id for t in in_group] == [group.short_id]
    assert len(await svc.list_tasks(OWNER, OWNER, is_group=False)) == 2

    with pytest.raises(TaskNotFoundError):
        await svc.cancel_task(OWNER, private.short_id, GROUP, is_group=True)
    with pytest.raises(TaskNotFoundError):
        await svc.cancel_task(OTHER, private.short_id, OTHER, is_group=False)
    await svc.cancel_task(OWNER, private.short_id, OWNER, is_group=False)
    with pytest.raises(TaskNotFoundError):
        await svc.cancel_task(OWNER, private.short_id, OWNER, is_group=False)


async def test_once_reminder_sent_then_deactivated(svc, clock, sender):
    await svc.create_task(OWNER, OWNER, message="Angkat jemuran", delay_minutes=30)
    assert await svc.run_due() == 0

    clock.now = NOW + timedelta(minutes=30, seconds=5)
    assert await svc.run_due() == 1
    chat, text = sender.await_args.args
    assert chat == OWNER and "Angkat jemuran" in text and "terlambat" not in text

    assert await svc.run_due() == 0
    assert await svc.list_tasks(OWNER, OWNER, is_group=False) == []


async def test_daily_reminder_advances(svc, clock, sender, repo):
    await svc.create_task(OWNER, OWNER, message="Minum obat", recurrence="daily", time_of_day="12:00")
    clock.now = wib(2026, 11, 6, 12, 0, 10)
    assert await svc.run_due() == 1
    assert "hapus 1" in sender.await_args.args[1]
    [task] = await repo.list_active(OWNER)
    assert task.next_run_at == wib(2026, 11, 7, 12, 0) and task.run_count == 1


async def test_overdue_once_is_sent_late_and_stale_recurring_is_skipped(svc, clock, sender, repo):
    await svc.create_task(OWNER, OWNER, message="Sekali", time_of_day="11:00")
    await svc.create_task(OWNER, OWNER, message="Harian", recurrence="daily", time_of_day="11:00")

    clock.now = wib(2026, 11, 6, 20, 0)  # bot mati 9 jam
    assert await svc.run_due() == 1
    assert "Sekali" in sender.await_args.args[1] and "terlambat" in sender.await_args.args[1]

    [daily] = await repo.list_active(OWNER)
    assert daily.message == "Harian" and daily.next_run_at == wib(2026, 11, 7, 11, 0) and daily.run_count == 0


async def test_send_failure_retries_then_gives_up(svc, clock, sender, repo):
    await svc.create_task(OWNER, OWNER, message="x", delay_minutes=1)
    clock.now = NOW + timedelta(minutes=2)
    sender.side_effect = RuntimeError("offline")
    for attempt in range(1, MAX_SEND_FAILURES):
        assert await svc.run_due() == 0
        [task] = await repo.list_active(OWNER)
        assert task.fail_count == attempt
    await svc.run_due()
    assert await repo.list_active(OWNER) == []


async def test_finance_report_uses_builder(svc, clock, sender):
    task = await svc.create_task(OWNER, OWNER, kind="finance_report", weekday="senin", time_of_day="07:00")
    assert task.recurrence == Recurrence.WEEKLY and task.kind == TaskKind.FINANCE_REPORT
    clock.now = wib(2026, 11, 9, 7, 0, 5)
    assert await svc.run_due() == 1
    assert sender.await_args.args[1] == "LAPORAN"


# ── Worker ────────────────────────────────────────────────────────────────────


async def test_worker_waits_while_whatsapp_disconnected(svc, clock, sender):
    await svc.create_task(OWNER, OWNER, message="x", delay_minutes=1)
    clock.now = NOW + timedelta(minutes=2)
    gateway = MagicMock()
    gateway.is_connected = AsyncMock(return_value=False)
    worker = SchedulerWorker(svc, gateway)
    assert await worker.tick() == 0
    sender.assert_not_awaited()
    gateway.is_connected.return_value = True
    assert await worker.tick() == 1


# ── AI tool executor ──────────────────────────────────────────────────────────


async def test_tool_executor_create_list_cancel(svc):
    ex = ReminderToolExecutor(svc)
    user, chat = JID.parse(OWNER), JID.parse(OWNER)

    out = json.loads(await ex.execute(
        "reminder_create",
        {"message": "Bayar listrik", "recurrence": "monthly", "day_of_month": 5, "time": "09:00"},
        user, chat,
    ))
    assert out["status"] == "success" and out["number"] == 1 and "tanggal 5" in out["repeat"]

    out = json.loads(await ex.execute(
        "reminder_create", {"message": "Rapat", "date": "2026-11-10", "time": "14:00"}, user, chat,
    ))
    assert "10 Nov 2026 14:00" in out["next_run"]

    listing = json.loads(await ex.execute("reminder_list", {}, user, chat))
    assert [r["number"] for r in listing["reminders"]] == [2, 1]

    out = json.loads(await ex.execute("reminder_cancel", {"number": 1}, user, chat))
    assert out["status"] == "success"
    out = json.loads(await ex.execute("reminder_cancel", {"number": 1}, user, chat))
    assert out["status"] == "error"

    out = json.loads(await ex.execute("reminder_create", {"message": "x"}, user, chat))
    assert out["status"] == "error" and "kapan" in out["message"]


# ── Command parsing ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("30m angkat jemuran", {"delay_minutes": 30, "message": "angkat jemuran"}),
        ("2j cek oven", {"delay_minutes": 120, "message": "cek oven"}),
        ("08:00 harian minum obat", {"time_of_day": "08:00", "recurrence": "daily", "message": "minum obat"}),
        ("senin 07.30 rapat", {"weekday": "senin", "recurrence": "weekly", "time_of_day": "07:30",
                               "message": "rapat"}),
        ("tgl5 09:00 bayar listrik", {"day_of_month": 5, "recurrence": "monthly", "time_of_day": "09:00",
                                      "message": "bayar listrik"}),
    ],
)
def test_parse_create(text, expected):
    assert _parse_create(text.split()) == expected


def test_parse_create_date_and_report():
    parsed = _parse_create("2026-12-01 09:00 bayar pajak".split())
    assert parsed["run_at"] == wib(2026, 12, 1, 9, 0) and parsed["message"] == "bayar pajak"
    report = _parse_create("senin 07:00 laporan".split())
    assert report["kind"] == TaskKind.FINANCE_REPORT and report["message"] == ""


async def test_command_creates_and_lists(svc):
    ctx = MagicMock()
    ctx.reply = AsyncMock()
    ctx.message.sender_jid = JID.parse(OWNER)
    ctx.message.chat_jid = JID.parse(OWNER)
    handler = ReminderCommandHandler(svc)

    ctx.command.args = ["15:00", "telepon", "ibu"]
    await handler.handle(ctx)
    assert "Jadwal Tersimpan" in ctx.reply.await_args.args[0]

    ctx.command.args = []
    await handler.handle(ctx)
    assert "telepon ibu" in ctx.reply.await_args.args[0]

    ctx.command.args = ["hapus", "9"]
    await handler.handle(ctx)
    assert "tidak ditemukan" in ctx.reply.await_args.args[0]


# ── Routing ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, wanted",
    [
        ("ingetin aku minum obat tiap hari jam 8", True),
        ("ingatkan bayar listrik tiap tanggal 5", True),
        ("hapus pengingat nomor 2", True),
        ("kirim laporan keuangan tiap senin jam 7", True),
        ("budget makan tiap bulan 1jt", False),
        ("tolong ingat ya aku suka kopi", False),
        ("catat pengeluaran 20rb kopi", False),
    ],
)
def test_reminder_intent_detection(text, wanted):
    assert wants_reminder_tools(text) is wanted


def test_reminder_overrides_finance_tools():
    policy = ContextPolicyManager.get_policy(
        intent="finance",
        text="ingetin bayar listrik tiap tanggal 5",
        settings=Settings(),
        tools_enabled=True,
        reminders_enabled=True,
    )
    names = {t.name for t in policy.tools or []}
    assert "reminder_create" in names
    assert "finance_add_expense" not in names
    assert policy.intent == "memory"


def test_reminder_tools_absent_when_disabled():
    policy = ContextPolicyManager.get_policy(
        intent="chat", text="ingetin minum obat jam 8", settings=Settings(), reminders_enabled=False,
    )
    assert policy.tools is None


def test_local_time_helper_sanity():
    assert to_local(NOW).hour == 10


async def test_failed_state_save_after_claim_does_not_resend(svc, clock, sender, repo):
    """Klaim sebelum kirim: gagal simpan -> pesan belum terkirim (bukan terkirim berulang)."""
    await svc.create_task(OWNER, OWNER, message="x", delay_minutes=1)
    clock.now = NOW + timedelta(minutes=2)
    original = repo.save_run_state
    repo.save_run_state = AsyncMock(side_effect=RuntimeError("database is locked"))
    assert await svc.run_due() == 0
    sender.assert_not_awaited()
    repo.save_run_state = original
    assert await svc.run_due() == 1
    assert await svc.run_due() == 0
    assert sender.await_count == 1


async def test_send_failure_restores_schedule_for_retry(svc, clock, sender, repo):
    await svc.create_task(OWNER, OWNER, message="Harian", recurrence="daily", time_of_day="12:00")
    clock.now = wib(2026, 11, 6, 12, 0, 5)
    sender.side_effect = RuntimeError("offline")
    await svc.run_due()
    [task] = await repo.list_active(OWNER)
    assert task.next_run_at == wib(2026, 11, 6, 12, 0) and task.run_count == 0 and task.fail_count == 1
    sender.side_effect = None
    assert await svc.run_due() == 1
    [task] = await repo.list_active(OWNER)
    assert task.next_run_at == wib(2026, 11, 7, 12, 0) and task.run_count == 1 and task.fail_count == 0


# ── Grup: hanya admin yang boleh membuat/menghapus pengingat ─────────────────


async def test_ai_tool_in_group_requires_admin(svc):
    group, user = JID.parse(GROUP), JID.parse(OWNER)
    args = {"message": "Rapat", "delay_minutes": 10}

    non_admin = ReminderToolExecutor(svc, is_group_admin=AsyncMock(return_value=False))
    out = json.loads(await non_admin.execute("reminder_create", args, user, group))
    assert out["status"] == "error" and "admin" in out["message"]

    broken = ReminderToolExecutor(svc, is_group_admin=AsyncMock(side_effect=RuntimeError("timeout")))
    out = json.loads(await broken.execute("reminder_create", args, user, group))
    assert out["status"] == "error" and "memastikan" in out["message"]  # fail closed

    admin_check = AsyncMock(return_value=True)
    admin = ReminderToolExecutor(svc, is_group_admin=admin_check)
    out = json.loads(await admin.execute("reminder_create", args, user, group))
    assert out["status"] == "success"
    admin_check.assert_awaited_once_with(group, user)

    out = json.loads(await non_admin.execute("reminder_cancel", {"number": out["number"]}, user, group))
    assert out["status"] == "error"
    listing = json.loads(await non_admin.execute("reminder_list", {}, user, group))
    assert listing["status"] == "success"  # melihat daftar tetap boleh

    # Chat pribadi tidak butuh cek admin.
    private = ReminderToolExecutor(svc, is_group_admin=AsyncMock(side_effect=AssertionError("no check")))
    out = json.loads(await private.execute("reminder_create", args, user, user))
    assert out["status"] == "success"


def _group_ctx(args, is_admin):
    ctx = MagicMock()
    ctx.reply = AsyncMock()
    ctx.message.sender_jid = JID.parse(OWNER)
    ctx.message.chat_jid = JID.parse(GROUP)
    ctx.command.args = args
    ctx.command.name = "pengingat"
    ctx.group_mgmt_uc.is_admin = AsyncMock(return_value=is_admin)
    return ctx


async def test_command_in_group_requires_admin(svc, repo):
    handler = ReminderCommandHandler(svc)

    ctx = _group_ctx(["10m", "rapat"], is_admin=False)
    await handler.handle(ctx)
    assert "admin grup" in ctx.reply.await_args.args[0]
    assert await repo.list_active(OWNER) == []

    ctx = _group_ctx(["10m", "rapat"], is_admin=True)
    await handler.handle(ctx)
    assert "Jadwal Tersimpan" in ctx.reply.await_args.args[0]

    ctx = _group_ctx(["hapus", "1"], is_admin=False)
    await handler.handle(ctx)
    assert "admin grup" in ctx.reply.await_args.args[0]
    assert len(await repo.list_active(OWNER)) == 1

    ctx = _group_ctx([], is_admin=False)  # daftar boleh untuk semua anggota
    await handler.handle(ctx)
    assert "rapat" in ctx.reply.await_args.args[0]
    ctx.group_mgmt_uc.is_admin.assert_not_awaited()
