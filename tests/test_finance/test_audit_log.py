"""Riwayat audit untuk data finance yang dihapus."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.features.finance.formatter import format_audit_log
from whatsapp_platform.features.finance.service import FinanceService
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)

OWNER = "628111@s.whatsapp.net"
OTHER = "628222@s.whatsapp.net"


@pytest.fixture
async def svc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield FinanceService(SQLAlchemyFinanceRepository(factory))
    await engine.dispose()


async def _setup(svc: FinanceService):
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("500000"))
    return await svc.add_expense(
        OWNER, Decimal("25000"), description="makan siang",
        category_name="Makanan & Minuman", account_id=acc.id,
    )


@pytest.mark.asyncio
async def test_delete_transaction_is_audited(svc: FinanceService) -> None:
    tx = await _setup(svc)
    assert await svc.delete_transaction(OWNER, tx.id)

    log = await svc.get_audit_log(OWNER)
    assert len(log) == 1
    e = log[0]
    assert (e.entity_type, e.action, e.entity_id) == ("transaction", "delete", tx.id)
    assert e.snapshot["amount"] == "25000.00"
    assert e.snapshot["description"] == "makan siang"
    assert e.snapshot["account_name"] == "BCA"
    assert e.snapshot["category_name"] == "Makanan & Minuman"
    text = format_audit_log(log)
    assert "makan siang" in text and "Rp 25.000" in text


@pytest.mark.asyncio
async def test_delete_budget_is_audited(svc: FinanceService) -> None:
    await svc.set_budget(OWNER, "Makanan & Minuman", Decimal("1000000"))
    await svc.delete_budget(OWNER, "Makanan & Minuman")

    (e,) = await svc.get_audit_log(OWNER)
    assert (e.entity_type, e.action) == ("budget", "delete")
    assert e.snapshot["amount"] == "1000000.00"
    assert e.snapshot["category_name"] == "Makanan & Minuman"
    assert "Rp 1.000.000" in format_audit_log([e])


@pytest.mark.asyncio
async def test_delete_account_is_audited(svc: FinanceService) -> None:
    await svc.create_account(OWNER, "Dana", AccountType.EWALLET, Decimal("10000"))
    await svc.delete_account(OWNER, "Dana")

    (e,) = await svc.get_audit_log(OWNER)
    assert (e.entity_type, e.action) == ("account", "delete")
    assert e.snapshot["name"] == "Dana"
    assert "Dana" in format_audit_log([e])


@pytest.mark.asyncio
async def test_reset_snapshots_every_row(svc: FinanceService) -> None:
    await _setup(svc)
    await svc.set_budget(OWNER, "Makanan & Minuman", Decimal("1000000"))
    counts = await svc.reset_all_data(OWNER)

    log = await svc.get_audit_log(OWNER, limit=100)
    assert all(e.action == "reset" for e in log)
    assert len(log) == sum(counts.values())
    assert {e.entity_type for e in log} == {"transaction", "budget", "account", "category"}
    assert await svc.get_audit_log(OWNER, limit=100, entity_type="budget")


@pytest.mark.asyncio
async def test_audit_log_is_per_owner_and_empty_message(svc: FinanceService) -> None:
    tx = await _setup(svc)
    await svc.delete_transaction(OWNER, tx.id)
    assert await svc.get_audit_log(OTHER) == []
    assert format_audit_log([]) == "Belum ada riwayat data yang dihapus."


@pytest.mark.asyncio
async def test_failed_delete_writes_no_audit(svc: FinanceService) -> None:
    with pytest.raises(Exception):
        await svc.delete_transaction(OWNER, "tidak-ada")
    assert await svc.get_audit_log(OWNER) == []
