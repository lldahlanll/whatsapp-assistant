"""Budget berulang tiap bulan + peringatan saat pemakaian melewati 80% / 100%."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.features.finance.formatter import format_budget_alert
from whatsapp_platform.features.finance.service import FinanceService
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)
from whatsapp_platform.shared.utils.timezone import now_local

OWNER = "628111@s.whatsapp.net"


@pytest.fixture
async def svc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield FinanceService(SQLAlchemyFinanceRepository(factory))
    await engine.dispose()


def _prev_month() -> tuple[int, int]:
    n = now_local()
    return (n.year - 1, 12) if n.month == 1 else (n.year, n.month - 1)


def _next_month() -> tuple[int, int]:
    n = now_local()
    return (n.year + 1, 1) if n.month == 12 else (n.year, n.month + 1)


# ── Recurring ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_carries_over_into_current_month(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)

    now = now_local()
    budgets = await svc.list_budgets(OWNER)  # bulan berjalan
    assert len(budgets) == 1
    assert budgets[0].budget.amount == Decimal("1000000")
    assert (budgets[0].budget.month, budgets[0].budget.year) == (now.month, now.year)
    assert budgets[0].spent == Decimal("0")  # pemakaian tidak ikut terbawa

    # Idempotent: membaca lagi tidak menggandakan.
    assert len(await svc.list_budgets(OWNER)) == 1


@pytest.mark.asyncio
async def test_carry_over_uses_latest_amount(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    await svc.set_budget(OWNER, "makan", Decimal("1500000"), month=pm, year=py)
    assert (await svc.list_budgets(OWNER))[0].budget.amount == Decimal("1500000")


@pytest.mark.asyncio
async def test_existing_current_month_budget_not_overwritten(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    await svc.set_budget(OWNER, "makan", Decimal("700000"))  # bulan berjalan
    budgets = await svc.list_budgets(OWNER)
    assert len(budgets) == 1
    assert budgets[0].budget.amount == Decimal("700000")


@pytest.mark.asyncio
async def test_delete_stops_recurrence(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    assert await svc.delete_budget(OWNER, "makan")  # menyalin lalu menghapus bulan ini
    assert await svc.list_budgets(OWNER) == []
    assert await svc.list_budgets(OWNER) == []  # tidak hidup lagi saat dibaca ulang


@pytest.mark.asyncio
async def test_set_again_after_delete_recurs_again(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    await svc.delete_budget(OWNER, "makan")
    await svc.set_budget(OWNER, "makan", Decimal("800000"))
    assert (await svc.list_budgets(OWNER))[0].budget.amount == Decimal("800000")


@pytest.mark.asyncio
async def test_no_carry_over_into_other_months(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    ny, nm = _next_month()
    assert await svc.list_budgets(OWNER, month=nm, year=ny) == []
    # Bulan sebelum budget pertama juga kosong.
    assert await svc.list_budgets(OWNER, month=pm, year=py - 1) == []


@pytest.mark.asyncio
async def test_carry_over_is_per_owner(svc: FinanceService) -> None:
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    assert await svc.list_budgets("other@s.whatsapp.net") == []


# ── Alert ─────────────────────────────────────────────────────────────────────


async def _spend(svc: FinanceService, account_id: str, amount: int):
    return await svc.add_expense(
        OWNER, Decimal(amount), description="x", category_name="Makanan & Minuman", account_id=account_id
    )


@pytest.mark.asyncio
async def test_alert_only_when_threshold_newly_crossed(svc: FinanceService) -> None:
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("10000000"))
    await svc.set_budget(OWNER, "makan", Decimal("1000000"))

    tx = await _spend(svc, acc.id, 700_000)  # 70%
    assert await svc.get_budget_alert(OWNER, tx) is None

    tx = await _spend(svc, acc.id, 150_000)  # 85% → melewati 80
    alert = await svc.get_budget_alert(OWNER, tx)
    assert alert is not None and alert.threshold == 80
    text = format_budget_alert(alert)
    assert "hampir habis" in text and "85%" in text and "Rp 150.000" in text

    tx = await _spend(svc, acc.id, 50_000)  # 90%, sudah di atas 80 → diam
    assert await svc.get_budget_alert(OWNER, tx) is None

    tx = await _spend(svc, acc.id, 110_000)  # 100%+ → melewati 100
    alert = await svc.get_budget_alert(OWNER, tx)
    assert alert is not None and alert.threshold == 100
    assert "terlewati" in format_budget_alert(alert)
    assert "Lebih Rp 10.000" in format_budget_alert(alert)


@pytest.mark.asyncio
async def test_single_big_expense_reports_highest_threshold(svc: FinanceService) -> None:
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("10000000"))
    await svc.set_budget(OWNER, "makan", Decimal("1000000"))
    alert = await svc.get_budget_alert(OWNER, await _spend(svc, acc.id, 1_000_000))
    assert alert is not None and alert.threshold == 100
    assert "habis!" in format_budget_alert(alert)  # tepat 100%, belum lewat


@pytest.mark.asyncio
async def test_no_alert_without_budget_or_for_other_category(svc: FinanceService) -> None:
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("10000000"))
    assert await svc.get_budget_alert(OWNER, await _spend(svc, acc.id, 500_000)) is None
    await svc.set_budget(OWNER, "bensin", Decimal("100000"))  # Transport
    assert await svc.get_budget_alert(OWNER, await _spend(svc, acc.id, 500_000)) is None


@pytest.mark.asyncio
async def test_alert_uses_carried_over_budget(svc: FinanceService) -> None:
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("10000000"))
    py, pm = _prev_month()
    await svc.set_budget(OWNER, "makan", Decimal("1000000"), month=pm, year=py)
    alert = await svc.get_budget_alert(OWNER, await _spend(svc, acc.id, 900_000))
    assert alert is not None and alert.threshold == 80


@pytest.mark.asyncio
async def test_alert_failure_never_raises(svc: FinanceService) -> None:
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("10000000"))
    tx = await _spend(svc, acc.id, 10_000)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    svc._repo.get_budget_progress = boom  # type: ignore[method-assign]
    assert await svc.get_budget_alert(OWNER, tx) is None


# ── Fast path ─────────────────────────────────────────────────────────────────


def test_fast_path_appends_budget_alert() -> None:
    import json

    raw = json.dumps({
        "status": "success", "amount": 50000, "account_name": "BCA",
        "category_name": "Makanan & Minuman", "description": "makan", "new_balance": 1000,
        "budget_alert": "⚠️ *Budget hampir habis.*",
    })
    out = try_finance_mutation_fast_path("finance_add_expense", raw)
    assert out is not None and out.rstrip().endswith("⚠️ *Budget hampir habis.*")
    raw2 = json.dumps({"status": "success", "amount": 1, "account_name": "BCA", "budget_alert": None})
    assert "Budget" not in try_finance_mutation_fast_path("finance_add_expense", raw2)
