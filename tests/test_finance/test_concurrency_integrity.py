"""Integritas data finance di bawah konkurensi (pesan yang diproses bersamaan).

Memakai database SQLite berbasis file (bukan :memory:) agar perilaku lock/WAL sama dengan produksi.
"""

import asyncio
import dataclasses
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.domain.exceptions import FinanceTransactionConflictError
from whatsapp_platform.features.finance.default_categories import ALL_DEFAULT_CATEGORIES
from whatsapp_platform.features.finance.service import FinanceService
from whatsapp_platform.infrastructure.database.base import Base, create_engine_and_session_factory
from whatsapp_platform.infrastructure.database.migration_backup import snapshot_database
from whatsapp_platform.infrastructure.database.repositories.finance_repo import SQLAlchemyFinanceRepository

OWNER = "628111222333@s.whatsapp.net"


@pytest.fixture
async def env(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"
    engine, factory = create_engine_and_session_factory(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyFinanceRepository(
        factory, pre_destructive_snapshot=lambda reason: snapshot_database(url, tmp_path, reason)
    )
    yield FinanceService(repo), repo, engine, tmp_path
    await engine.dispose()


async def test_sqlite_pragmas_are_applied(env) -> None:
    _, _, engine, _ = env
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() >= 5000


async def test_concurrent_first_use_does_not_duplicate_default_categories(env) -> None:
    svc, repo, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("1000000"))

    results = await asyncio.gather(
        *[
            svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id, idempotency_key=f"wa:M{i}:x")
            for i in range(4)
        ],
        return_exceptions=True,
    )

    assert all(not isinstance(r, Exception) for r in results), results
    categories = await repo.get_categories(OWNER)
    assert len(categories) == len(ALL_DEFAULT_CATEGORIES)
    assert len({(c.category_type, c.name) for c in categories}) == len(categories)
    # Pengguna tetap bisa mencatat setelahnya (dulu: MultipleResultsFound selamanya).
    await svc.add_expense(OWNER, Decimal("5000"), "kopi", account_id=acc.id, idempotency_key="wa:after:x")


async def test_same_message_processed_concurrently_is_recorded_once(env) -> None:
    svc, _, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    await svc.ensure_defaults(OWNER)

    results = await asyncio.gather(
        *[
            svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id, idempotency_key="wa:MSG1:abc")
            for _ in range(5)
        ]
    )

    assert len({tx.id for tx in results}) == 1
    assert len(await svc.get_recent_transactions(OWNER, limit=20)) == 1
    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("90000")


async def test_idempotency_key_is_scoped_per_owner(env) -> None:
    svc, _, _, _ = env
    other = "628999@s.whatsapp.net"
    a = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    b = await svc.create_account(other, "BCA", AccountType.BANK, Decimal("100000"))

    t1 = await svc.add_expense(OWNER, Decimal("1000"), "x", account_id=a.id, idempotency_key="wa:SAME:k")
    t2 = await svc.add_expense(other, Decimal("1000"), "x", account_id=b.id, idempotency_key="wa:SAME:k")

    assert t1.id != t2.id


async def test_edit_cannot_apply_to_reversed_transaction(env) -> None:
    svc, repo, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id)
    await svc.reverse_transaction(OWNER, tx.id)

    stale = dataclasses.replace(tx, amount=Decimal("20000"))
    with pytest.raises(FinanceTransactionConflictError):
        await repo.update_transaction_atomic(stale, {acc.id: Decimal("-10000")})

    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("100000")


async def test_reverse_rejects_stale_amount_after_concurrent_edit(env) -> None:
    svc, repo, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id)
    # Edit menang lebih dulu: amount di DB jadi 15.000.
    await repo.update_transaction_atomic(dataclasses.replace(tx, amount=Decimal("15000")), {acc.id: Decimal("-5000")})

    # Reversal yang dihitung dari data lama (10.000) harus ditolak, bukan membuat saldo salah.
    stale_reversal = dataclasses.replace(tx, id="rev-1", human_tx_id=None, idempotency_key=None, reversal_of_id=tx.id)
    with pytest.raises(FinanceTransactionConflictError):
        await repo.reverse_transaction_atomic(tx.id, OWNER, stale_reversal, {acc.id: Decimal("10000")})

    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("85000")


async def test_reset_takes_snapshot_first_and_snapshot_is_restorable(env) -> None:
    svc, _, _, tmp_path = env
    await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))

    await svc.reset_all_data(OWNER)

    snapshots = list((tmp_path / "backups" / "snapshots").glob("app-pre-reset-*.db"))
    assert len(snapshots) == 1
    conn = sqlite3.connect(snapshots[0])
    try:
        assert conn.execute("SELECT COUNT(*) FROM finance_accounts WHERE owner_jid = ?", (OWNER,)).fetchone()[0] == 1
    finally:
        conn.close()
    assert await svc.get_accounts(OWNER) == []


async def test_reset_is_aborted_when_snapshot_fails(env) -> None:
    svc, _, engine, _ = env
    from whatsapp_platform.infrastructure.database.base import create_engine_and_session_factory as _factory

    def boom(_reason: str):
        raise OSError("disk full")

    second_engine, factory = _factory(str(engine.url))
    try:
        failing = FinanceService(SQLAlchemyFinanceRepository(factory, pre_destructive_snapshot=boom))
        await failing.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))

        with pytest.raises(OSError):
            await failing.reset_all_data(OWNER)
    finally:
        await second_engine.dispose()

    assert len(await svc.get_accounts(OWNER)) == 1


# ── Soft delete ──────────────────────────────────────────────────────────────


async def test_delete_transaction_keeps_row_for_audit_and_restores_balance(env) -> None:
    svc, _, engine, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id)

    assert await svc.delete_transaction(OWNER, tx.id) is True

    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("100000")
    assert await svc.get_recent_transactions(OWNER, limit=20) == []
    async with engine.connect() as conn:
        query = text("SELECT deleted_at, is_reversed FROM finance_transactions WHERE id = :i")
        row = (await conn.execute(query, {"i": tx.id})).one()
    assert row.deleted_at is not None and row.is_reversed


async def test_deleted_transaction_cannot_be_deleted_or_found_again(env) -> None:
    from whatsapp_platform.features.finance.service import TransactionNotFoundError

    svc, _, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id)
    await svc.delete_transaction(OWNER, tx.id)

    with pytest.raises(TransactionNotFoundError):
        await svc.delete_transaction(OWNER, tx.id)
    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("100000")


async def test_concurrent_deletes_restore_balance_only_once(env) -> None:
    svc, repo, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(OWNER, Decimal("10000"), "kopi", account_id=acc.id)

    results = await asyncio.gather(*[repo.delete_transaction(tx.id, OWNER) for _ in range(4)])

    assert sorted(results) == [False, False, False, True]
    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("100000")


# ── Nominal & presisi ────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-5"), Decimal("NaN"), Decimal("Infinity"), Decimal("1E+13")])
async def test_invalid_amounts_are_rejected(env, bad: Decimal) -> None:
    from whatsapp_platform.features.finance.service import InvalidAmountError

    svc, _, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    with pytest.raises(InvalidAmountError):
        await svc.add_expense(OWNER, bad, "x", account_id=acc.id)


async def test_amount_is_rounded_to_two_decimals(env) -> None:
    svc, _, _, _ = env
    acc = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100"))
    tx = await svc.add_expense(OWNER, Decimal("10.005"), "x", account_id=acc.id)
    assert tx.amount == Decimal("10.01")


async def test_float_drift_does_not_reject_spending_exact_balance(env) -> None:
    svc, _, _, _ = env
    acc = await svc.create_account(OWNER, "Kas", AccountType.CASH, Decimal("0"))
    for _ in range(8):
        await svc.add_income(OWNER, Decimal("0.10"), "x", account_id=acc.id)

    # 8 x 0.1 = 0.7999999999999999 sebagai float; pengeluaran 0.80 harus tetap lolos.
    await svc.add_expense(OWNER, Decimal("0.80"), "x", account_id=acc.id)
    assert (await svc.get_accounts(OWNER))[0].balance == Decimal("0.00")


def test_expired_pending_confirmations_are_pruned(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from whatsapp_platform.infrastructure.finance import tool_executor as mod

    executor = mod.FinanceToolExecutor(MagicMock())
    clock = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock["t"])
    executor._confirmed_by_user("a", "reset_data", "all", "m1", False)
    assert len(executor._pending_confirmations) == 1

    clock["t"] += mod._CONFIRMATION_TTL_SECONDS + 1
    executor._confirmed_by_user("b", "reset_data", "all", "m2", False)

    assert list(executor._pending_confirmations) == [("b", "reset_data", "all")]
