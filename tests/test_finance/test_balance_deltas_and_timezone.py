"""Atomic relative balance updates (no lost updates) and WIB-based calendar periods."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    FinanceAccount,
    FinanceTransaction,
    TransactionType,
)
from whatsapp_platform.features.finance.service import (
    FinanceService,
    InsufficientBalanceError,
    TransactionAlreadyReversedError,
)
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)
from whatsapp_platform.shared.utils.timezone import (
    day_bounds_utc,
    month_bounds_utc,
    parse_local_datetime,
)

OWNER = "user1@s.whatsapp.net"


@pytest.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SQLAlchemyFinanceRepository(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    await engine.dispose()


async def _account(repo: SQLAlchemyFinanceRepository, balance: str) -> FinanceAccount:
    return await repo.create_account(
        FinanceAccount(
            id="acc-1",
            owner_jid=OWNER,
            name="BCA",
            account_type=AccountType.BANK,
            currency="IDR",
            balance=Decimal(balance),
            is_active=True,
            created_at=datetime.now(UTC),
        )
    )


def _stale_reads(repo: SQLAlchemyFinanceRepository, snapshot: FinanceAccount) -> None:
    """Simulasikan pesan lain yang mengubah saldo setelah service membaca saldo."""

    async def get_account_by_id(account_id: str, owner_jid: str) -> FinanceAccount:
        return snapshot

    repo.get_account_by_id = get_account_by_id  # type: ignore[method-assign]


async def _balance(repo: SQLAlchemyFinanceRepository) -> Decimal:
    accounts = await repo.get_accounts(OWNER)
    return accounts[0].balance


async def test_concurrent_change_is_not_overwritten(repo: SQLAlchemyFinanceRepository) -> None:
    snapshot = await _account(repo, "100000")
    svc = FinanceService(repo)
    # Pesan lain sudah memotong 30rb, tapi service masih melihat saldo 100rb
    await svc.add_expense(OWNER, Decimal("30000"), account_id="acc-1")
    _stale_reads(repo, snapshot)

    await svc.add_expense(OWNER, Decimal("50000"), account_id="acc-1")

    # Dulu: saldo ditimpa jadi 100rb - 50rb = 50rb (potongan 30rb hilang)
    assert await _balance(repo) == Decimal("20000")


async def test_overdraw_rejected_atomically(repo: SQLAlchemyFinanceRepository) -> None:
    snapshot = await _account(repo, "100000")
    svc = FinanceService(repo)
    await svc.add_expense(OWNER, Decimal("70000"), account_id="acc-1")
    _stale_reads(repo, snapshot)

    with pytest.raises(InsufficientBalanceError):
        await svc.add_expense(OWNER, Decimal("50000"), account_id="acc-1")

    assert await _balance(repo) == Decimal("30000")
    # Transaksi yang gagal ikut di-rollback
    assert len(await repo.get_transactions(OWNER)) == 1


async def test_double_reversal_rejected(repo: SQLAlchemyFinanceRepository) -> None:
    await _account(repo, "100000")
    svc = FinanceService(repo)
    tx = await svc.add_expense(OWNER, Decimal("40000"), account_id="acc-1")
    stale_tx = await repo.get_transaction_by_id(tx.id, OWNER)

    await svc.reverse_transaction(OWNER, tx.id)
    # Reversal kedua yang membaca status lama (belum reversed) harus ditolak oleh DB
    original_get = repo.get_transaction_by_id

    async def stale_get(tx_id: str, owner_jid: str):
        return stale_tx if tx_id == tx.id else await original_get(tx_id, owner_jid)

    repo.get_transaction_by_id = stale_get  # type: ignore[method-assign]
    with pytest.raises(TransactionAlreadyReversedError):
        await svc.reverse_transaction(OWNER, tx.id)

    assert await _balance(repo) == Decimal("100000")


def test_month_bounds_follow_wib() -> None:
    start, end = month_bounds_utc(2026, 11)
    assert start == datetime(2026, 10, 31, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 30, 17, 0, tzinfo=UTC)


def test_day_bounds_follow_wib() -> None:
    start, end = day_bounds_utc(date(2026, 11, 2))
    assert start == datetime(2026, 11, 1, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 2, 17, 0, tzinfo=UTC)


def test_naive_input_is_local_time() -> None:
    assert parse_local_datetime("2026-11-02") == datetime(2026, 11, 1, 17, 0, tzinfo=UTC)
    assert parse_local_datetime("2026-11-02T10:00:00+00:00") == datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    assert parse_local_datetime("bukan tanggal") is None


async def test_early_morning_on_first_counts_in_new_month(repo: SQLAlchemyFinanceRepository) -> None:
    await _account(repo, "1000000")
    # 1 Nov 05:00 WIB = 31 Okt 22:00 UTC
    await repo.save_transaction_atomic(
        FinanceTransaction(
            id="tx-early",
            owner_jid=OWNER,
            account_id="acc-1",
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("25000"),
            category_id=None,
            description="Sarapan",
            transaction_date=datetime(2026, 10, 31, 22, 0, tzinfo=UTC),
            transfer_to_account_id=None,
            created_at=datetime.now(UTC),
        ),
        {"acc-1": Decimal("-25000")},
    )

    november = await repo.get_monthly_summary(OWNER, 2026, 11)
    october = await repo.get_monthly_summary(OWNER, 2026, 10)

    assert november.total_expense == Decimal("25000")
    assert october.total_expense == Decimal("0")
