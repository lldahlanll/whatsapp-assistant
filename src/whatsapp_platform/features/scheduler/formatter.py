"""Format teks pengingat & daftar jadwal untuk WhatsApp."""

from __future__ import annotations

from datetime import datetime

from whatsapp_platform.domain.entities.schedule import Recurrence, ScheduledTask, TaskKind
from whatsapp_platform.shared.utils.timezone import to_local

_DAY_NAMES = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def format_when(dt: datetime) -> str:
    """'Jumat, 07 Nov 2026 08:00 WIB'."""
    local = to_local(dt)
    return (
        f"{_DAY_NAMES[local.weekday()]}, {local.day:02d} {_MONTH_NAMES[local.month - 1]} "
        f"{local.year} {local:%H:%M} WIB"
    )


def format_recurrence(task: ScheduledTask) -> str:
    local = to_local(task.next_run_at)
    hm = f"{local:%H:%M}"
    if task.recurrence == Recurrence.DAILY:
        return f"tiap hari {hm}"
    if task.recurrence == Recurrence.WEEKDAYS:
        return f"tiap hari kerja (Sen-Jum) {hm}"
    if task.recurrence == Recurrence.WEEKLY:
        return f"tiap {_DAY_NAMES[local.weekday()]} {hm}"
    if task.recurrence == Recurrence.MONTHLY:
        return f"tiap tanggal {task.anchor_day or local.day} {hm}"
    return "sekali"


def task_title(task: ScheduledTask) -> str:
    if task.kind == TaskKind.FINANCE_REPORT:
        return "Laporan keuangan"
    return task.message


def format_due_reminder(task: ScheduledTask, late_since: datetime | None = None) -> str:
    text = f"⏰ *Pengingat*\n\n{task.message}"
    if late_since is not None:
        text += f"\n\n_(Jadwal asli {format_when(late_since)}, terkirim terlambat.)_"
    if task.recurrence != Recurrence.ONCE:
        text += f"\n\n_Berulang {format_recurrence(task)} · hentikan: `!pengingat hapus {task.short_id}`_"
    return text


def format_task_created(task: ScheduledTask) -> str:
    lines = [
        "*Jadwal Tersimpan*",
        "",
        f"• No: {task.short_id}",
        f"• Isi: {task_title(task)}",
        f"• Kirim berikutnya: {format_when(task.next_run_at)}",
        f"• Pengulangan: {format_recurrence(task)}",
    ]
    return "\n".join(lines)


def format_task_list(tasks: list[ScheduledTask]) -> str:
    if not tasks:
        return (
            "Belum ada pengingat aktif.\n"
            "Buat lewat chat, contoh: _'ingetin minum obat tiap hari jam 8'_, "
            "atau `!pengingat 08:00 harian minum obat`."
        )
    lines = [f"*Pengingat Aktif* ({len(tasks)})", "━━━━━━━━━━━━━━━━━━"]
    for t in tasks:
        lines.append(f"*{t.short_id}.* {task_title(t)}")
        lines.append(f"    {format_when(t.next_run_at)} · {format_recurrence(t)}")
    lines.append("")
    lines.append("_Hapus: `!pengingat hapus <no>`_")
    return "\n".join(lines)
