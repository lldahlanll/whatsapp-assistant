"""Hitung waktu kirim berikutnya untuk tugas berulang.

Perhitungan dilakukan pada jam dinding lokal (WIB) supaya "tiap hari jam 08:00" tetap jam 08:00,
lalu dikonversi ke UTC untuk disimpan.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

from whatsapp_platform.domain.entities.schedule import Recurrence
from whatsapp_platform.shared.utils.timezone import LOCAL_TZ, to_local


def _localize(wall: datetime) -> datetime:
    return wall.replace(tzinfo=LOCAL_TZ).astimezone(UTC)


def _add_months(wall: datetime, months: int, anchor_day: int) -> datetime:
    total = wall.month - 1 + months
    year, month = wall.year + total // 12, total % 12 + 1
    day = min(anchor_day, calendar.monthrange(year, month)[1])
    return wall.replace(year=year, month=month, day=day)


def next_occurrence(
    current: datetime, recurrence: Recurrence, anchor_day: int | None = None
) -> datetime | None:
    """Kejadian setelah ``current`` (UTC). None untuk tugas sekali jalan."""
    if recurrence == Recurrence.ONCE:
        return None
    wall = to_local(current).replace(tzinfo=None)
    if recurrence == Recurrence.DAILY:
        wall += timedelta(days=1)
    elif recurrence == Recurrence.WEEKDAYS:
        wall += timedelta(days=1)
        while wall.weekday() >= 5:
            wall += timedelta(days=1)
    elif recurrence == Recurrence.WEEKLY:
        wall += timedelta(days=7)
    elif recurrence == Recurrence.MONTHLY:
        wall = _add_months(wall, 1, anchor_day or wall.day)
    return _localize(wall)


def first_occurrence(start: datetime, recurrence: Recurrence) -> datetime:
    """Untuk WEEKDAYS: geser ke hari kerja jika ``start`` jatuh di akhir pekan."""
    if recurrence != Recurrence.WEEKDAYS:
        return start
    wall = to_local(start).replace(tzinfo=None)
    while wall.weekday() >= 5:
        wall += timedelta(days=1)
    return _localize(wall)


def advance_past(
    current: datetime, now: datetime, recurrence: Recurrence, anchor_day: int | None = None
) -> datetime | None:
    """Kejadian pertama setelah ``now`` — melewati jadwal yang terlewat saat bot mati."""
    nxt = next_occurrence(current, recurrence, anchor_day)
    while nxt is not None and nxt <= now:
        nxt = next_occurrence(nxt, recurrence, anchor_day)
    return nxt
