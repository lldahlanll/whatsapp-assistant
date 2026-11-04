"""finance_get_transactions: default bulan berjalan, bulan lalu atas permintaan."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor
from whatsapp_platform.shared.utils.timezone import month_bounds_utc, now_local


def _executor() -> tuple[FinanceToolExecutor, AsyncMock]:
    svc = MagicMock()
    svc.get_recent_transactions = AsyncMock(return_value=[])
    ex = FinanceToolExecutor.__new__(FinanceToolExecutor)
    ex._svc = svc
    return ex, svc.get_recent_transactions


@pytest.mark.asyncio
async def test_default_is_current_month() -> None:
    ex, get = _executor()
    out = json.loads(await ex._get_transactions("u", {}))
    now = now_local()
    start, end = month_bounds_utc(now.year, now.month)
    kw = get.call_args.kwargs
    assert kw["date_from"] == start
    assert start <= kw["date_to"] < end
    assert kw["limit"] == 31  # 30 + 1 untuk deteksi terpotong
    assert out["period"] == "this_month"
    assert out["period_month"] == f"{now.year:04d}-{now.month:02d}"
    assert out["truncated"] is False


@pytest.mark.asyncio
async def test_last_month_on_request() -> None:
    ex, get = _executor()
    out = json.loads(await ex._get_transactions("u", {"period": "last_month"}))
    now = now_local()
    y, m = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    start, _ = month_bounds_utc(y, m)
    assert get.call_args.kwargs["date_from"] == start
    assert out["period"] == "last_month"
    assert out["period_month"] == f"{y:04d}-{m:02d}"


@pytest.mark.asyncio
async def test_explicit_dates_override_period() -> None:
    ex, get = _executor()
    out = json.loads(
        await ex._get_transactions("u", {"date_from": "2026-01-05", "period": "last_month"})
    )
    kw = get.call_args.kwargs
    assert kw["date_from"] == datetime(2026, 1, 4, 17, 0, tzinfo=UTC)
    assert kw["date_to"] is None
    assert out["period"] == "custom"
    assert kw["limit"] == 11


@pytest.mark.asyncio
async def test_explicit_month_and_year() -> None:
    ex, get = _executor()
    out = json.loads(await ex._get_transactions("u", {"month": 1, "year": 2026}))
    start, end = month_bounds_utc(2026, 1)
    kw = get.call_args.kwargs
    assert kw["date_from"] == start
    assert start <= kw["date_to"] < end
    assert out["period"] == "month"
    assert out["period_month"] == "2026-01"


@pytest.mark.asyncio
async def test_month_without_year_infers_year() -> None:
    ex, _ = _executor()
    now = now_local()
    out = json.loads(await ex._get_transactions("u", {"month": 12}))
    expected_year = now.year if now.month >= 12 else now.year - 1
    assert out["period_month"] == f"{expected_year:04d}-12"
    out = json.loads(await ex._get_transactions("u", {"month": now.month}))
    assert out["period_month"] == f"{now.year:04d}-{now.month:02d}"


@pytest.mark.asyncio
async def test_invalid_month_is_rejected() -> None:
    ex, get = _executor()
    for bad in (0, 13, "abc"):
        out = json.loads(await ex._get_transactions("u", {"month": bad}))
        assert out["status"] == "error"
    get.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_dates_beat_month() -> None:
    ex, get = _executor()
    out = json.loads(
        await ex._get_transactions("u", {"date_from": "2026-03-01", "month": 1})
    )
    assert out["period"] == "custom"
    assert get.call_args.kwargs["date_to"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("year", "month", "days"),
    [(2026, 1, 31), (2026, 2, 28), (2028, 2, 29), (2026, 4, 30), (2026, 12, 31)],
)
async def test_month_range_follows_real_calendar(year: int, month: int, days: int) -> None:
    from whatsapp_platform.shared.utils.timezone import to_local

    ex, get = _executor()
    await ex._get_transactions("u", {"month": month, "year": year})
    kw = get.call_args.kwargs
    first, last = to_local(kw["date_from"]), to_local(kw["date_to"])
    assert (first.year, first.month, first.day) == (year, month, 1)
    assert (last.year, last.month, last.day) == (year, month, days)
    assert (last.hour, last.minute) == (23, 59)
