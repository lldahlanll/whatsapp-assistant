"""Zona waktu lokal aplikasi (default Asia/Jakarta / WIB).

Konvensi: waktu disimpan di database sebagai UTC. Semua yang bersifat
"kalender" (hari ini, bulan ini, batas laporan bulanan, tanggal yang
ditampilkan ke user) dihitung di zona waktu lokal lalu dikonversi ke UTC.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _load_local_tz() -> tzinfo:
    name = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # Image Docker slim bisa tidak punya tzdata. WIB tidak punya DST,
        # jadi offset tetap +07:00 tetap akurat.
        return timezone(timedelta(hours=7), "WIB")


LOCAL_TZ: tzinfo = _load_local_tz()


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def to_local(dt: datetime) -> datetime:
    """Konversi ke waktu lokal. Datetime naive dianggap UTC (format penyimpanan DB)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ)


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Rentang [awal, akhir) satu hari kalender lokal, dalam UTC."""
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def month_bounds_utc(year: int, month: int) -> tuple[datetime, datetime]:
    """Rentang [awal, akhir) satu bulan kalender lokal, dalam UTC."""
    start = datetime(year, month, 1, tzinfo=LOCAL_TZ)
    end = datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ) if month == 12 else datetime(year, month + 1, 1, tzinfo=LOCAL_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def parse_local_datetime(val: str | None) -> datetime | None:
    """Parse string ISO dari user/LLM. Tanpa offset dianggap waktu lokal. Hasil dalam UTC."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(UTC)


def parse_local_date(val: str | None) -> date | None:
    """Ambil tanggal kalender lokal dari string ISO ('2026-11-02' atau datetime lengkap)."""
    dt = parse_local_datetime(val)
    return to_local(dt).date() if dt else None
