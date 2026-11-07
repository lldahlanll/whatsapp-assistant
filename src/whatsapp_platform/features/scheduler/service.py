"""SchedulerService — membuat, mendaftar, membatalkan, dan menjalankan tugas terjadwal."""

from __future__ import annotations

import calendar
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.domain.entities.schedule import Recurrence, ScheduledTask, TaskKind
from whatsapp_platform.domain.repositories.schedule_repository import IScheduleRepository
from whatsapp_platform.features.scheduler.formatter import format_due_reminder, format_when
from whatsapp_platform.features.scheduler.recurrence import advance_past, first_occurrence
from whatsapp_platform.shared.utils.timezone import LOCAL_TZ, now_local, to_local

if TYPE_CHECKING:
    from whatsapp_platform.features.finance.service import FinanceService

logger = structlog.get_logger()

MAX_ACTIVE_TASKS_PER_USER = 30
MAX_MESSAGE_CHARS = 500
MAX_DAYS_AHEAD = 366
MIN_LEAD_SECONDS = 30
# Jadwal berulang yang terlewat lebih dari ini (mis. bot mati semalaman) dilewati, tidak dikirim telat.
STALE_AFTER = timedelta(hours=6)
# Gagal kirim berturut-turut sebanyak ini -> jadwal dimajukan agar tidak macet selamanya.
MAX_SEND_FAILURES = 5
DEFAULT_TIME = "08:00"

SendFn = Callable[[str, str], Awaitable[object]]
ReportFn = Callable[[str], Awaitable[str]]

WEEKDAYS: dict[str, int] = {
    "senin": 0, "monday": 0, "mon": 0,
    "selasa": 1, "tuesday": 1, "tue": 1,
    "rabu": 2, "wednesday": 2, "wed": 2,
    "kamis": 3, "thursday": 3, "thu": 3,
    "jumat": 4, "jum'at": 4, "friday": 4, "fri": 4,
    "sabtu": 5, "saturday": 5, "sat": 5,
    "minggu": 6, "ahad": 6, "sunday": 6, "sun": 6,
}

_TIME_PATTERN = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*$")


class SchedulerError(Exception):
    """Pesan aman ditampilkan ke pengguna."""


class TaskNotFoundError(SchedulerError):
    pass


def parse_time_of_day(value: str) -> tuple[int, int]:
    m = _TIME_PATTERN.match(value or "")
    if not m:
        raise SchedulerError(f"Format jam '{value}' tidak valid. Gunakan HH:MM, contoh 08:30.")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        raise SchedulerError(f"Jam '{value}' tidak valid.")
    return hour, minute


def parse_recurrence(value: str | Recurrence | None) -> Recurrence:
    if isinstance(value, Recurrence):
        return value
    v = (value or "once").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "once": Recurrence.ONCE, "sekali": Recurrence.ONCE, "none": Recurrence.ONCE,
        "daily": Recurrence.DAILY, "harian": Recurrence.DAILY, "setiap_hari": Recurrence.DAILY,
        "tiap_hari": Recurrence.DAILY,
        "weekdays": Recurrence.WEEKDAYS, "hari_kerja": Recurrence.WEEKDAYS, "weekday": Recurrence.WEEKDAYS,
        "weekly": Recurrence.WEEKLY, "mingguan": Recurrence.WEEKLY,
        "monthly": Recurrence.MONTHLY, "bulanan": Recurrence.MONTHLY,
    }
    if v not in aliases:
        raise SchedulerError(
            f"Pola ulang '{value}' tidak dikenal. Pilih: sekali, harian, hari kerja, mingguan, bulanan."
        )
    return aliases[v]


def resolve_first_run(
    now: datetime,
    *,
    delay_minutes: int | None = None,
    run_at: datetime | None = None,
    time_of_day: str | None = None,
    weekday: str | None = None,
    day_of_month: int | None = None,
) -> datetime:
    """Waktu kirim pertama (UTC) dari kombinasi parameter yang diberikan pengguna/LLM.

    Prioritas: delay_minutes > run_at > (day_of_month | weekday | jam saja).
    Hasil bisa di masa lalu (mis. run_at hari ini jam yang sudah lewat); pemanggil yang memutuskan.
    """
    if delay_minutes is not None:
        if delay_minutes < 1:
            raise SchedulerError("Jeda pengingat minimal 1 menit.")
        return now + timedelta(minutes=delay_minutes)
    if run_at is not None:
        return run_at
    if time_of_day is None and weekday is None and day_of_month is None:
        raise SchedulerError("Sebutkan kapan pengingat dikirim (jam, tanggal, atau 'X menit lagi').")

    hour, minute = parse_time_of_day(time_of_day or DEFAULT_TIME)
    local_now = to_local(now)
    today = local_now.replace(tzinfo=None, hour=hour, minute=minute, second=0, microsecond=0)

    if day_of_month is not None:
        if not 1 <= day_of_month <= 31:
            raise SchedulerError("Tanggal harus 1-31.")
        year, month = today.year, today.month
        for _ in range(2):
            day = min(day_of_month, calendar.monthrange(year, month)[1])
            wall = today.replace(year=year, month=month, day=day)
            if wall.replace(tzinfo=LOCAL_TZ) > local_now:
                break
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return wall.replace(tzinfo=LOCAL_TZ).astimezone(UTC)

    if weekday is not None:
        wd = WEEKDAYS.get(weekday.strip().lower())
        if wd is None:
            raise SchedulerError(f"Nama hari '{weekday}' tidak dikenal.")
        wall = today + timedelta(days=(wd - today.weekday()) % 7)
        if wall.replace(tzinfo=LOCAL_TZ) <= local_now:
            wall += timedelta(days=7)
        return wall.replace(tzinfo=LOCAL_TZ).astimezone(UTC)

    wall = today
    if wall.replace(tzinfo=LOCAL_TZ) <= local_now:
        wall += timedelta(days=1)
    return wall.replace(tzinfo=LOCAL_TZ).astimezone(UTC)


class SchedulerService:
    def __init__(
        self,
        repo: IScheduleRepository,
        send: SendFn | None = None,
        build_finance_report: ReportFn | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repo
        self._send = send
        self._build_finance_report = build_finance_report
        self._clock = clock or (lambda: datetime.now(UTC))

    def now(self) -> datetime:
        return self._clock()

    # ── Membuat / melihat / membatalkan ───────────────────────────────────────

    async def create_task(
        self,
        owner_jid: str,
        chat_jid: str,
        *,
        message: str = "",
        kind: TaskKind | str = TaskKind.REMINDER,
        recurrence: Recurrence | str | None = None,
        is_group: bool = False,
        delay_minutes: int | None = None,
        run_at: datetime | None = None,
        time_of_day: str | None = None,
        weekday: str | None = None,
        day_of_month: int | None = None,
    ) -> ScheduledTask:
        try:
            kind = TaskKind(kind)
        except ValueError as exc:
            raise SchedulerError(f"Jenis jadwal '{kind}' tidak dikenal.") from exc
        rec = parse_recurrence(recurrence)
        now = self.now()

        text = " ".join((message or "").split())
        if kind == TaskKind.REMINDER and not text:
            raise SchedulerError("Isi pengingatnya apa? Contoh: 'minum obat'.")
        if len(text) > MAX_MESSAGE_CHARS:
            raise SchedulerError(f"Isi pengingat maksimal {MAX_MESSAGE_CHARS} karakter.")
        if kind == TaskKind.FINANCE_REPORT:
            if is_group:
                raise SchedulerError("Laporan keuangan terjadwal hanya bisa dibuat di chat pribadi.")
            if rec == Recurrence.ONCE:
                rec = Recurrence.WEEKLY if weekday else Recurrence.MONTHLY if day_of_month else Recurrence.DAILY
            if not any(v is not None for v in (delay_minutes, run_at, time_of_day, weekday, day_of_month)):
                time_of_day = DEFAULT_TIME

        if await self._repo.count_active(owner_jid) >= MAX_ACTIVE_TASKS_PER_USER:
            raise SchedulerError(
                f"Batas {MAX_ACTIVE_TASKS_PER_USER} jadwal aktif sudah tercapai. Hapus yang tidak dipakai dulu."
            )

        first = resolve_first_run(
            now,
            delay_minutes=delay_minutes,
            run_at=run_at,
            time_of_day=time_of_day,
            weekday=weekday,
            day_of_month=day_of_month,
        )
        if first <= now + timedelta(seconds=MIN_LEAD_SECONDS):
            if rec == Recurrence.ONCE:
                raise SchedulerError(f"Waktu {format_when(first)} sudah lewat. Pilih waktu yang akan datang.")
            advanced = advance_past(first, now + timedelta(seconds=MIN_LEAD_SECONDS), rec, day_of_month)
            if advanced is None:  # tidak mungkin untuk jadwal berulang
                raise SchedulerError("Gagal menghitung jadwal berikutnya.")
            first = advanced
        first = first_occurrence(first, rec)
        if first > now + timedelta(days=MAX_DAYS_AHEAD):
            raise SchedulerError("Jadwal maksimal 1 tahun ke depan.")

        anchor = None
        if rec == Recurrence.MONTHLY:
            anchor = day_of_month or to_local(first).day

        task = await self._repo.create(
            ScheduledTask(
                id=str(uuid.uuid4()),
                owner_jid=owner_jid,
                chat_jid=chat_jid,
                kind=kind,
                message=text,
                recurrence=rec,
                next_run_at=first,
                anchor_day=anchor,
                is_active=True,
                created_at=now,
            )
        )
        logger.info(
            "Scheduled task created",
            owner=owner_jid, kind=kind.value, recurrence=rec.value, next_run=first.isoformat(),
        )
        return task

    async def list_tasks(self, owner_jid: str, chat_jid: str, is_group: bool) -> list[ScheduledTask]:
        # Di grup hanya tampilkan jadwal grup itu, agar pengingat pribadi tidak terlihat anggota lain.
        return await self._repo.list_active(owner_jid, chat_jid if is_group else None)

    async def cancel_task(
        self, owner_jid: str, short_id: int, chat_jid: str, is_group: bool
    ) -> ScheduledTask:
        task = await self._repo.get_by_short_id(owner_jid, short_id)
        if task is None or not task.is_active or (is_group and task.chat_jid != chat_jid):
            raise TaskNotFoundError(f"Jadwal nomor {short_id} tidak ditemukan.")
        await self._repo.deactivate(task.id)
        logger.info("Scheduled task cancelled", owner=owner_jid, short_id=short_id)
        return task

    # ── Eksekusi ──────────────────────────────────────────────────────────────

    async def run_due(self) -> int:
        """Kirim semua tugas yang jatuh tempo. Mengembalikan jumlah pesan terkirim."""
        now = self.now()
        sent = 0
        for task in await self._repo.get_due(now):
            try:
                if await self._run_task(task, now):
                    sent += 1
            except Exception as exc:  # satu tugas rusak tidak boleh menghentikan yang lain
                logger.error("Scheduled task crashed", task=task.id, error=str(exc), exc_info=True)
        return sent

    async def _run_task(self, task: ScheduledTask, now: datetime) -> bool:
        """Klaim dulu (majukan jadwal di DB), baru kirim.

        Jika simpan status gagal setelah pesan terkirim, urutan sebaliknya membuat pesan yang sama
        terkirim ulang tiap putaran. Lebih baik satu pengingat hilang daripada spam berulang.
        """
        overdue = now - task.next_run_at
        due_at, prev_active, prev_fail, prev_last = task.next_run_at, task.is_active, task.fail_count, task.last_run_at
        stale = task.recurrence != Recurrence.ONCE and overdue > STALE_AFTER

        text: str | None = None
        if stale:
            logger.info("Skipping stale scheduled occurrence", task=task.id, overdue=str(overdue))
        else:
            try:
                text = await self._render(task, overdue)
            except Exception as exc:  # noqa: BLE001 — gagal render dicoba ulang seperti gagal kirim
                return await self._record_failure(task, exc)

        nxt = advance_past(due_at, now, task.recurrence, task.anchor_day)
        task.is_active = nxt is not None
        task.next_run_at = nxt or due_at
        task.fail_count = 0
        if text is not None:
            task.run_count += 1
            task.last_run_at = now
        await self._repo.save_run_state(task)  # klaim; gagal di sini -> belum terkirim, aman diulang
        if text is None:
            return False

        try:
            if self._send is None:
                raise RuntimeError("Scheduler sender not configured")
            await self._send(task.chat_jid, text)
            return True
        except Exception as exc:  # noqa: BLE001 — gagal kirim apa pun dicoba ulang, bukan crash
            # Kembalikan ke kejadian yang gagal agar dicoba lagi di putaran berikutnya.
            task.next_run_at, task.is_active, task.fail_count = due_at, prev_active, prev_fail
            task.run_count, task.last_run_at = task.run_count - 1, prev_last
            return await self._record_failure(task, exc)

    async def _record_failure(self, task: ScheduledTask, exc: Exception) -> bool:
        task.fail_count += 1
        logger.warning("Scheduled task send failed", task=task.id, attempt=task.fail_count, error=str(exc))
        if task.fail_count >= MAX_SEND_FAILURES:
            logger.error("Scheduled task gave up after repeated failures", task=task.id)
            nxt = advance_past(task.next_run_at, self.now(), task.recurrence, task.anchor_day)
            task.is_active = nxt is not None
            task.next_run_at = nxt or task.next_run_at
            task.fail_count = 0
        await self._repo.save_run_state(task)
        return False

    async def _render(self, task: ScheduledTask, overdue: timedelta) -> str:
        if task.kind == TaskKind.FINANCE_REPORT:
            if self._build_finance_report is None:
                raise RuntimeError("Finance report builder not configured")
            return await self._build_finance_report(task.owner_jid)
        late_since = task.next_run_at if overdue > timedelta(minutes=10) else None
        return format_due_reminder(task, late_since)


async def build_finance_report_text(finance_service: FinanceService, owner_jid: str) -> str:
    """Laporan bulan berjalan; pada tanggal 1 kirim laporan lengkap bulan sebelumnya."""
    from whatsapp_platform.features.finance.formatter import format_monthly_report

    today = now_local()
    if today.day == 1:
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    else:
        year, month = today.year, today.month
    summary = await finance_service.get_monthly_report(owner_jid, year=year, month=month)
    return "*Laporan Keuangan Terjadwal*\n\n" + format_monthly_report(summary)
