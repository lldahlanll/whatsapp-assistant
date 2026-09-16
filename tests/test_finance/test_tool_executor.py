from datetime import UTC, datetime
from decimal import Decimal
import json
from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    FinanceAccount,
    FinanceTransaction,
    TransactionType,
)
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.finance.service import (
    AccountRequiredError,
    InsufficientBalanceError,
)
from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor


@pytest.fixture
def user_jid() -> JID:
    return JID.parse("628123456789@s.whatsapp.net")


@pytest.fixture
def chat_jid() -> JID:
    return JID.parse("628123456789@s.whatsapp.net")


@pytest.fixture
def mock_service() -> AsyncMock:
    svc = AsyncMock()
    svc._repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_tool_executor_expense_success(mock_service: AsyncMock, user_jid: JID, chat_jid: JID) -> None:
    executor = FinanceToolExecutor(mock_service)

    bca_acc = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("950000"),
        is_active=True,
        created_at=None, # type: ignore[arg-type]
    )
    mock_service.find_account_by_name.return_value = bca_acc
    mock_service._repo.get_account_by_id.return_value = bca_acc

    tx = FinanceTransaction(
        id="tx-100",
        human_tx_id="TXN-20260818-000100",
        owner_jid=str(user_jid),
        account_id=bca_acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan siang",
        transaction_date=None, # type: ignore[arg-type]
        transfer_to_account_id=None,
        created_at=None, # type: ignore[arg-type]
        account_name="BCA",
    )
    mock_service.add_expense.return_value = tx

    res_raw = await executor.execute(
        tool_name="finance_add_expense",
        arguments={"amount": 50000, "description": "Makan siang", "account_name": "BCA"},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["transaction_id"] == "TXN-20260818-000100"
    assert data["amount"] == 50000.0
    assert data["account_name"] == "BCA"


@pytest.mark.asyncio
async def test_tool_executor_insufficient_balance_error_code(mock_service: AsyncMock, user_jid: JID, chat_jid: JID) -> None:
    executor = FinanceToolExecutor(mock_service)
    gopay = FinanceAccount(id="acc-1", owner_jid=str(user_jid), name="GoPay", account_type=AccountType.EWALLET, currency="IDR", balance=Decimal("100000"), is_active=True, created_at=None) # type: ignore[arg-type]
    mock_service.find_account_by_name.return_value = gopay
    mock_service.add_expense.side_effect = InsufficientBalanceError("Saldo GoPay Rp 100.000, sedangkan transaksi Rp 150.000. Kurang Rp 50.000.")

    res_raw = await executor.execute(
        tool_name="finance_add_expense",
        arguments={"amount": 150000, "account_name": "GoPay"},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "error"
    assert data["error_code"] == "INSUFFICIENT_BALANCE"
    assert "GoPay" in data["message"]


@pytest.mark.asyncio
async def test_tool_executor_account_not_found_error_code(mock_service: AsyncMock, user_jid: JID, chat_jid: JID) -> None:
    executor = FinanceToolExecutor(mock_service)
    mock_service.find_account_by_name.return_value = None

    res_raw = await executor.execute(
        tool_name="finance_add_expense",
        arguments={"amount": 50000, "account_name": "Blu"},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "error"
    assert data["error_code"] == "ACCOUNT_NOT_FOUND"
    assert "Blu" in data["message"]


@pytest.mark.asyncio
async def test_tool_executor_account_required_error_code(mock_service: AsyncMock, user_jid: JID, chat_jid: JID) -> None:
    executor = FinanceToolExecutor(mock_service)
    mock_service.add_expense.side_effect = AccountRequiredError("Rekening/dompet belum ditentukan.")

    res_raw = await executor.execute(
        tool_name="finance_add_expense",
        arguments={"amount": 50000},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "error"
    assert data["error_code"] == "ACCOUNT_REQUIRED"


@pytest.mark.asyncio
async def test_tool_executor_expense_with_custom_date(
    mock_service: AsyncMock, user_jid: JID, chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    bca_acc = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("950000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_service.find_account_by_name.return_value = bca_acc
    mock_service._repo.get_account_by_id.return_value = bca_acc

    tx = FinanceTransaction(
        id="tx-101",
        human_tx_id="TXN-20260818-000101",
        owner_jid=str(user_jid),
        account_id=bca_acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan malam kemarin",
        transaction_date=datetime(2026, 8, 23, 19, 0, tzinfo=UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service.add_expense.return_value = tx

    res_raw = await executor.execute(
        tool_name="finance_add_expense",
        arguments={
            "amount": 50000,
            "description": "Makan malam kemarin",
            "account_name": "BCA",
            "date": "2026-08-23",
        },
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["date"] == "2026-08-23"
    mock_service.add_expense.assert_called_once()
    assert mock_service.add_expense.call_args[1]["date"] == datetime(2026, 8, 23, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_tool_executor_delete_account_needs_confirmation(
    mock_service: AsyncMock, user_jid: JID, chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    bca_acc = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("5000000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_service.find_account_by_name.return_value = bca_acc

    # Call with confirm=False (default)
    res_raw = await executor.execute(
        tool_name="finance_delete_account",
        arguments={"name": "BCA"},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "need_confirmation"
    assert data["account_name"] == "BCA"
    assert data["balance"] == 5000000.0
    mock_service.delete_account.assert_not_called()


@pytest.mark.asyncio
async def test_tool_executor_delete_account_confirmed(
    mock_service: AsyncMock, user_jid: JID, chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    bca_acc = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("5000000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_service.find_account_by_name.return_value = bca_acc
    mock_service.delete_account.return_value = bca_acc

    # Call with confirm=True
    res_raw = await executor.execute(
        tool_name="finance_delete_account",
        arguments={"name": "BCA", "confirm": True},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["account_name"] == "BCA"
    mock_service.delete_account.assert_called_once_with(str(user_jid), bca_acc.id)


@pytest.mark.asyncio
async def test_tool_executor_update_transaction_with_new_amount(
    mock_service: AsyncMock, user_jid: JID, chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    orig_tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260913-000001",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan siang",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    updated_tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260913-000001",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("25000"),
        category_id=None,
        description="Makan siang",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service._repo.get_transaction_by_id.return_value = orig_tx
    mock_service.correct_transaction.return_value = updated_tx

    res_raw = await executor.execute(
        tool_name="finance_update_transaction",
        arguments={"transaction_id": "TXN-20260913-000001", "new_amount": 25000},
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["transaction_id"] == "TXN-20260913-000001"
    assert data["new_amount"] == 25000.0
    mock_service.correct_transaction.assert_called_once_with(
        owner_jid=str(user_jid),
        original_tx_id="TXN-20260913-000001",
        new_amount=Decimal("25000"),
        new_description=None,
        new_category_name=None,
        new_account_id=None,
    )


@pytest.mark.asyncio
async def test_tool_executor_update_transaction_with_amount_and_string(
    mock_service: AsyncMock, user_jid: JID, chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    orig_tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260913-000001",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan siang",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    updated_tx = FinanceTransaction(
        id="tx-1",
        human_tx_id="TXN-20260913-000001",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("35000"),
        category_id=None,
        description="Makan siang enak",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service._repo.get_transaction_by_id.return_value = orig_tx
    mock_service.correct_transaction.return_value = updated_tx

    # Testing "amount" instead of "new_amount" and string "35rb"
    res_raw = await executor.execute(
        tool_name="finance_update_transaction",
        arguments={
            "transaction_id": "TXN-20260913-000001",
            "amount": "35rb",
            "description": "Makan siang enak",
        },
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["amount"] == 35000.0
    mock_service.correct_transaction.assert_called_once_with(
        owner_jid=str(user_jid),
        original_tx_id="TXN-20260913-000001",
        new_amount=Decimal("35000"),
        new_description="Makan siang enak",
        new_category_name=None,
        new_account_id=None,
    )


@pytest.mark.asyncio
async def test_tool_executor_update_transaction_keyword_fallback(mock_service: AsyncMock, user_jid: JID, chat_jid: JID) -> None:
    executor = FinanceToolExecutor(mock_service)
    tx = FinanceTransaction(
        id="tx-999",
        human_tx_id="TXN-20260913-40242D",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("5000"),
        category_id=None,
        description="Paket Data 3",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    updated_tx = FinanceTransaction(
        id="tx-999",
        human_tx_id="TXN-20260913-40242D",
        owner_jid=str(user_jid),
        account_id="acc-1",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Paket Data 3",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )

    # get_transaction_by_id returns None for keyword "paket data 3"
    mock_service._repo.get_transaction_by_id.return_value = None
    # search_transactions returns the matched transaction
    mock_service.search_transactions.return_value = [tx]
    mock_service.correct_transaction.return_value = updated_tx

    res_raw = await executor.execute(
        tool_name="finance_update_transaction",
        arguments={
            "transaction_id": "paket data 3",
            "new_amount": 50000,
        },
        user_jid=user_jid,
        chat_jid=chat_jid,
    )

    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["amount"] == 50000.0
    mock_service.search_transactions.assert_called_once_with(
        str(user_jid), keyword="paket data 3", limit=2
    )
    mock_service.correct_transaction.assert_called_once_with(
        owner_jid=str(user_jid),
        original_tx_id="tx-999",
        new_amount=Decimal("50000"),
        new_description=None,
        new_category_name=None,
        new_account_id=None,
    )



