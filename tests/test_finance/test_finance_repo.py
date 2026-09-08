"""Integration tests for SQLAlchemyFinanceRepository atomic operations, rollback, and persistence."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    FinanceAccount,
    FinanceTransaction,
    TransactionType,
)
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_repo_save_transaction_atomic_updates_balance(async_session_factory) -> None:
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    owner_jid = "user1@s.whatsapp.net"

    acc = await repo.create_account(
        FinanceAccount(
            id="acc-1",
            owner_jid=owner_jid,
            name="Kas",
            account_type=AccountType.CASH,
            currency="IDR",
            balance=Decimal("100000"),
            is_active=True,
            created_at=None,  # type: ignore[arg-type]
        )
    )

    tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260818-000001",
        idempotency_key="msg-1",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("25000"),
        category_id=None,
        description="Makan",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
    )

    saved = await repo.save_transaction_atomic(tx, {acc.id: Decimal("75000")})
    assert saved.id == "tx-1"
    assert saved.human_tx_id == "TXN-20260818-000001"

    updated_acc = await repo.get_account_by_id(acc.id, owner_jid)
    assert updated_acc is not None
    assert updated_acc.balance == Decimal("75000")


@pytest.mark.asyncio
async def test_repo_idempotency_lookup(async_session_factory) -> None:
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    owner_jid = "user1@s.whatsapp.net"

    acc = await repo.create_account(
        FinanceAccount(
            id="acc-1",
            owner_jid=owner_jid,
            name="Kas",
            account_type=AccountType.CASH,
            currency="IDR",
            balance=Decimal("100000"),
            is_active=True,
            created_at=None,  # type: ignore[arg-type]
        )
    )

    tx = FinanceTransaction(
        id="tx-idempotent-1",
        human_tx_id="TXN-20260818-000009",
        idempotency_key="unique-msg-999",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("50000"),
        category_id=None,
        description="Gaji",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
    )

    await repo.save_transaction_atomic(tx, {acc.id: Decimal("150000")})

    found = await repo.get_transaction_by_idempotency_key(owner_jid, "unique-msg-999")
    assert found is not None
    assert found.id == "tx-idempotent-1"

    not_found = await repo.get_transaction_by_idempotency_key(owner_jid, "non-existent")
    assert not_found is None


@pytest.mark.asyncio
async def test_repo_reverse_transaction_atomic(async_session_factory) -> None:
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    owner_jid = "user1@s.whatsapp.net"

    acc = await repo.create_account(
        FinanceAccount(
            id="acc-bca",
            owner_jid=owner_jid,
            name="BCA",
            account_type=AccountType.BANK,
            currency="IDR",
            balance=Decimal("500000"),
            is_active=True,
            created_at=None,  # type: ignore[arg-type]
        )
    )

    orig_tx = FinanceTransaction(
        id="tx-orig",
        human_tx_id="TXN-20260818-000010",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("100000"),
        category_id=None,
        description="Salah potong",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
    )
    await repo.save_transaction_atomic(orig_tx, {acc.id: Decimal("400000")})

    rev_tx = FinanceTransaction(
        id="tx-rev",
        human_tx_id="TXN-20260818-000011",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("100000"),
        category_id=None,
        description="Reversal of TXN-20260818-000010",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        reversal_of_id=orig_tx.id,
        created_at=None,  # type: ignore[arg-type]
    )

    rev_saved = await repo.reverse_transaction_atomic(
        original_tx_id=orig_tx.id,
        owner_jid=owner_jid,
        reversal_tx=rev_tx,
        balance_updates={acc.id: Decimal("500000")},
    )

    assert rev_saved.reversal_of_id == orig_tx.id

    fetched_orig = await repo.get_transaction_by_id(orig_tx.id, owner_jid)
    assert fetched_orig is not None
    assert fetched_orig.is_reversed is True

    fetched_acc = await repo.get_account_by_id(acc.id, owner_jid)
    assert fetched_acc is not None
    assert fetched_acc.balance == Decimal("500000")


@pytest.mark.asyncio
async def test_repo_delete_account(async_session_factory) -> None:
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    owner_jid = "user1@s.whatsapp.net"

    acc = await repo.create_account(
        FinanceAccount(
            id="acc-to-del",
            owner_jid=owner_jid,
            name="BCA",
            account_type=AccountType.BANK,
            currency="IDR",
            balance=Decimal("500000"),
            is_active=True,
            created_at=None,  # type: ignore[arg-type]
        )
    )

    accounts_before = await repo.get_accounts(owner_jid)
    assert len(accounts_before) == 1

    success = await repo.delete_account(acc.id, owner_jid)
    assert success is True

    accounts_after = await repo.get_accounts(owner_jid)
    assert len(accounts_after) == 0

    # Non-existent account delete
    success_none = await repo.delete_account("non-existent-id", owner_jid)
    assert success_none is False

