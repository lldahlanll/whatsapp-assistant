"""Unit & integration tests for FinanceService hardening rules."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    FinanceAccount,
    FinanceTransaction,
    TransactionType,
)
from whatsapp_platform.features.finance.service import (
    AccountRequiredError,
    FinanceService,
    InsufficientBalanceError,
)


@pytest.fixture
def owner_jid() -> str:
    return "user@s.whatsapp.net"


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_accounts = AsyncMock(return_value=[])
    repo.get_categories = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_income_adds_to_balance_atomically(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    cash_acc = FinanceAccount(
        id="acc-cash-1",
        owner_jid=owner_jid,
        name="Kas",
        account_type=AccountType.CASH,
        currency="IDR",
        balance=Decimal("100000"),
        is_active=True,
        created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_accounts.return_value = [cash_acc]
    mock_repo.get_account_by_id.return_value = cash_acc
    mock_repo.get_transaction_by_idempotency_key.return_value = None

    saved_tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260818-000001",
        owner_jid=owner_jid,
        account_id=cash_acc.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("50000"),
        category_id=None,
        description="Gaji freelance",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
        account_name="Kas",
    )
    mock_repo.save_transaction_atomic.return_value = saved_tx

    result = await svc.add_income(
        owner_jid=owner_jid,
        amount=Decimal("50000"),
        description="Gaji freelance",
        account_id=cash_acc.id,
    )

    assert result.amount == Decimal("50000")
    mock_repo.save_transaction_atomic.assert_called_once()
    balance_updates = mock_repo.save_transaction_atomic.call_args[0][1]
    assert balance_updates == {cash_acc.id: Decimal("150000")}


@pytest.mark.asyncio
async def test_expense_deducts_balance_atomically(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    cash_acc = FinanceAccount(
        id="acc-cash-1",
        owner_jid=owner_jid,
        name="Kas",
        account_type=AccountType.CASH,
        currency="IDR",
        balance=Decimal("100000"),
        is_active=True,
        created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_accounts.return_value = [cash_acc]
    mock_repo.get_account_by_id.return_value = cash_acc
    mock_repo.get_transaction_by_idempotency_key.return_value = None

    saved_tx = FinanceTransaction(
        id="tx-2",
        human_tx_id="TXN-20260818-000002",
        owner_jid=owner_jid,
        account_id=cash_acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("35000"),
        category_id=None,
        description="Makan siang",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
        account_name="Kas",
    )
    mock_repo.save_transaction_atomic.return_value = saved_tx

    result = await svc.add_expense(
        owner_jid=owner_jid,
        amount=Decimal("35000"),
        description="Makan siang",
        account_id=cash_acc.id,
    )

    assert result.amount == Decimal("35000")
    balance_updates = mock_repo.save_transaction_atomic.call_args[0][1]
    assert balance_updates == {cash_acc.id: Decimal("65000")}


@pytest.mark.asyncio
async def test_expense_fails_on_insufficient_balance(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    gopay_acc = FinanceAccount(
        id="acc-gopay-1",
        owner_jid=owner_jid,
        name="GoPay",
        account_type=AccountType.EWALLET,
        currency="IDR",
        balance=Decimal("100000"),
        is_active=True,
        created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_accounts.return_value = [gopay_acc]
    mock_repo.get_account_by_id.return_value = gopay_acc
    mock_repo.get_transaction_by_idempotency_key.return_value = None

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await svc.add_expense(
            owner_jid=owner_jid,
            amount=Decimal("150000"),
            description="Belanja",
            account_id=gopay_acc.id,
        )

    assert "GoPay" in str(exc_info.value)
    assert "100,000" in str(exc_info.value) or "100000" in str(exc_info.value)
    mock_repo.save_transaction_atomic.assert_not_called()


@pytest.mark.asyncio
async def test_transfer_preserves_total_net_worth(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    bca_acc = FinanceAccount(
        id="acc-bca-1",
        owner_jid=owner_jid,
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("1000000"),
        is_active=True,
        created_at=None,  # type: ignore[arg-type]
    )
    gopay_acc = FinanceAccount(
        id="acc-gopay-1",
        owner_jid=owner_jid,
        name="GoPay",
        account_type=AccountType.EWALLET,
        currency="IDR",
        balance=Decimal("200000"),
        is_active=True,
        created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_account_by_id.side_effect = lambda acc_id, jid: (
        bca_acc if acc_id == bca_acc.id else (gopay_acc if acc_id == gopay_acc.id else None)
    )
    mock_repo.get_transaction_by_idempotency_key.return_value = None

    saved_tx = FinanceTransaction(
        id="tx-3",
        human_tx_id="TXN-20260818-000003",
        owner_jid=owner_jid,
        account_id=bca_acc.id,
        transaction_type=TransactionType.TRANSFER,
        amount=Decimal("500000"),
        category_id=None,
        description="Top up GoPay",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=gopay_acc.id,
        created_at=None,  # type: ignore[arg-type]
        account_name="BCA",
        transfer_to_account_name="GoPay",
    )
    mock_repo.save_transaction_atomic.return_value = saved_tx

    result = await svc.transfer(
        owner_jid=owner_jid,
        amount=Decimal("500000"),
        from_account_id=bca_acc.id,
        to_account_id=gopay_acc.id,
        description="Top up GoPay",
    )

    assert result.amount == Decimal("500000")
    balance_updates = mock_repo.save_transaction_atomic.call_args[0][1]
    assert balance_updates[bca_acc.id] == Decimal("500000")
    assert balance_updates[gopay_acc.id] == Decimal("700000")
    # Total net worth invariant check: (1,000,000 + 200,000) == (500,000 + 700,000)
    assert (bca_acc.balance + gopay_acc.balance) == (balance_updates[bca_acc.id] + balance_updates[gopay_acc.id])


@pytest.mark.asyncio
async def test_idempotency_key_prevents_duplicate_transaction(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    existing_tx = FinanceTransaction(
        id="tx-existing-100",
        human_tx_id="TXN-20260818-000100",
        idempotency_key="msg-12345",
        owner_jid=owner_jid,
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan",
        transaction_date=None,  # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_transaction_by_idempotency_key.return_value = existing_tx

    res = await svc.add_expense(
        owner_jid=owner_jid,
        amount=Decimal("50000"),
        description="Makan",
        account_id="acc-1",
        idempotency_key="msg-12345",
    )

    assert res.id == "tx-existing-100"
    mock_repo.save_transaction_atomic.assert_not_called()


@pytest.mark.asyncio
async def test_account_resolution_raises_when_multiple_accounts_and_unspecified(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    acc1 = FinanceAccount(id="acc-1", owner_jid=owner_jid, name="BCA", account_type=AccountType.BANK, currency="IDR", balance=Decimal("100"), is_active=True, created_at=None) # type: ignore[arg-type]
    acc2 = FinanceAccount(id="acc-2", owner_jid=owner_jid, name="GoPay", account_type=AccountType.EWALLET, currency="IDR", balance=Decimal("100"), is_active=True, created_at=None) # type: ignore[arg-type]
    mock_repo.get_accounts.return_value = [acc1, acc2]

    with pytest.raises(AccountRequiredError):
        await svc.add_expense(
            owner_jid=owner_jid,
            amount=Decimal("10000"),
            description="Makan",
            account_id=None,
        )


@pytest.mark.asyncio
async def test_reversal_restores_balances_and_marks_original_reversed(mock_repo: AsyncMock, owner_jid: str) -> None:
    svc = FinanceService(mock_repo)
    acc = FinanceAccount(
        id="acc-bca-1",
        owner_jid=owner_jid,
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("450000"),
        is_active=True,
        created_at=None, # type: ignore[arg-type]
    )
    orig_tx = FinanceTransaction(
        id="tx-orig-1",
        human_tx_id="TXN-20260818-000001",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Salah catat",
        transaction_date=None, # type: ignore[arg-type]
        transfer_to_account_id=None,
        is_reversed=False,
        reversal_of_id=None,
        created_at=None, # type: ignore[arg-type]
    )
    mock_repo.get_transaction_by_id.return_value = orig_tx
    mock_repo.get_account_by_id.return_value = acc

    rev_result_tx = FinanceTransaction(
        id="tx-rev-2",
        human_tx_id="TXN-20260818-000002",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Reversal of TXN-20260818-000001",
        transaction_date=None, # type: ignore[arg-type]
        transfer_to_account_id=None,
        is_reversed=False,
        reversal_of_id=orig_tx.id,
        created_at=None, # type: ignore[arg-type]
    )
    mock_repo.reverse_transaction_atomic.return_value = rev_result_tx

    result = await svc.reverse_transaction(owner_jid, orig_tx.id, reason="Salah catat")

    assert result.reversal_of_id == orig_tx.id
    mock_repo.reverse_transaction_atomic.assert_called_once()
    balance_updates = mock_repo.reverse_transaction_atomic.call_args[1]["balance_updates"]
    # 450,000 + 50,000 == 500,000
    assert balance_updates[acc.id] == Decimal("500000")
