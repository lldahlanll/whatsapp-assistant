"""!pengingat — buat, lihat, dan hapus pengingat terjadwal tanpa lewat AI."""

from __future__ import annotations

import re

from whatsapp_platform.domain.entities.schedule import TaskKind
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.scheduler.formatter import format_task_created, format_task_list
from whatsapp_platform.features.scheduler.service import (
    WEEKDAYS,
    SchedulerError,
    SchedulerService,
)
from whatsapp_platform.shared.utils.timezone import parse_local_datetime

_HELP = (
    "*PENGINGAT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "`!pengingat` — daftar pengingat aktif\n"
    "`!pengingat 30m angkat jemuran` — 30 menit lagi (`2j` = 2 jam)\n"
    "`!pengingat 15:00 telepon ibu` — hari ini/besok jam 15:00\n"
    "`!pengingat 2026-12-01 09:00 bayar pajak` — tanggal tertentu\n"
    "`!pengingat 08:00 harian minum obat`\n"
    "`!pengingat 07:00 hari-kerja absen`\n"
    "`!pengingat senin 08:00 rapat mingguan`\n"
    "`!pengingat tgl5 09:00 bayar listrik` — bulanan tiap tanggal 5\n"
    "`!pengingat senin 07:00 laporan` — laporan keuangan mingguan (chat pribadi)\n"
    "`!pengingat hapus 3` — hapus pengingat no. 3\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "_Atau ngobrol biasa: 'ingetin minum obat tiap hari jam 8'_"
)

_RELATIVE = re.compile(r"^(\d{1,4})(m|mnt|menit|j|jam|h)$", re.IGNORECASE)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{1,2}[:.]\d{2}$")
_DAY_OF_MONTH = re.compile(r"^(?:tgl|tanggal)(\d{1,2})$", re.IGNORECASE)
_RECURRENCE_WORDS = {
    "sekali": "once", "harian": "daily", "hari-kerja": "weekdays", "harikerja": "weekdays",
    "mingguan": "weekly", "bulanan": "monthly",
}
_REPORT_WORDS = {"laporan", "laporan keuangan", "rekap", "rekap keuangan"}


class ReminderCommandHandler(BaseCommandHandler):
    def __init__(self, scheduler: SchedulerService, name: str = "pengingat") -> None:
        self._svc = scheduler
        self._name = name

    @property
    def command_name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Pengingat & laporan terjadwal (!pengingat help)"

    async def handle(self, ctx: CommandContext) -> None:
        args = list(ctx.command.args)
        owner = str(ctx.message.sender_jid)
        chat = str(ctx.message.chat_jid)
        is_group = ctx.message.chat_jid.is_group
        try:
            if not args or args[0].lower() in ("list", "daftar", "semua"):
                await ctx.reply(format_task_list(await self._svc.list_tasks(owner, chat, is_group)))
                return
            if args[0].lower() in ("help", "bantuan", "panduan"):
                await ctx.reply(_HELP)
                return
            if args[0].lower() in ("hapus", "delete", "batal", "stop"):
                if len(args) < 2 or not args[1].isdigit():
                    await ctx.reply("Format: `!pengingat hapus <no>`. Lihat nomornya dengan `!pengingat`.")
                    return
                task = await self._svc.cancel_task(owner, int(args[1]), chat, is_group)
                await ctx.reply(f"Pengingat no. {task.short_id} dihapus.")
                return

            task = await self._svc.create_task(owner, chat, is_group=is_group, **_parse_create(args))
            await ctx.reply(format_task_created(task))
        except SchedulerError as exc:
            await ctx.reply(f"❌ {exc}\n\nKetik `!pengingat help` untuk contoh.")


def _parse_create(args: list[str]) -> dict:
    """Ambil token waktu di depan, sisanya isi pengingat."""
    params: dict = {}
    date: str | None = None
    i = 0
    while i < len(args):
        tok = args[i].lower()
        if m := _RELATIVE.match(tok):
            n = int(m.group(1))
            params["delay_minutes"] = n * 60 if m.group(2).lower() in ("j", "jam", "h") else n
        elif _DATE.match(tok):
            date = tok
        elif _TIME.match(tok):
            params["time_of_day"] = tok.replace(".", ":")
        elif tok in _RECURRENCE_WORDS:
            params["recurrence"] = _RECURRENCE_WORDS[tok]
        elif tok in WEEKDAYS:
            params["weekday"] = tok
            params.setdefault("recurrence", "weekly")
        elif m := _DAY_OF_MONTH.match(tok):
            params["day_of_month"] = int(m.group(1))
            params.setdefault("recurrence", "monthly")
        else:
            break
        i += 1

    message = " ".join(args[i:]).strip()
    if message.lower() in _REPORT_WORDS:
        params["kind"] = TaskKind.FINANCE_REPORT
        message = ""
    params["message"] = message

    if date:
        run_at = parse_local_datetime(f"{date}T{params.pop('time_of_day', '08:00')}")
        if run_at is None:
            raise SchedulerError(f"Tanggal '{date}' tidak valid.")
        params["run_at"] = run_at
    return params
