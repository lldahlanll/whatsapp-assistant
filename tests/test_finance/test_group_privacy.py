"""Tests for Finance Group Chat Privacy Controls.

Validates that:
1. Read & management tools are blocked in group chats with a private-only redirect.
2. Mutation tools succeed in group chats, but balance fields are stripped.
3. Fast path suppresses balance displays in group chats.
4. Context policy selects group-specific finance system prompt in group chats.
"""

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
from whatsapp_platform.infrastructure.ai.constants import (
    AI_FINANCE_GROUP_SYSTEM_PROMPT,
    AI_FINANCE_SYSTEM_PROMPT,
)
from whatsapp_platform.infrastructure.ai.context_policy import ContextPolicyManager
from whatsapp_platform.infrastructure.ai.finance_fast_path import (
    GROUP_PRIVATE_TOOLS,
    is_group_blocked_tool,
    try_finance_mutation_fast_path,
)
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.finance.tool_executor import (
    GROUP_BLOCKED_TOOLS,
    FinanceToolExecutor,
)


@pytest.fixture
def user_jid() -> JID:
    return JID.parse("628123456789@s.whatsapp.net")


@pytest.fixture
def private_chat_jid() -> JID:
    return JID.parse("628123456789@s.whatsapp.net")


@pytest.fixture
def group_chat_jid() -> JID:
    return JID.parse("120363041234567890@g.us")


@pytest.fixture
def mock_service() -> AsyncMock:
    svc = AsyncMock()
    svc._repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_group_blocked_tools_return_private_only_error(
    mock_service: AsyncMock, user_jid: JID, group_chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)

    for tool_name in GROUP_BLOCKED_TOOLS:
        raw_res = await executor.execute(
            tool_name=tool_name,
            arguments={},
            user_jid=user_jid,
            chat_jid=group_chat_jid,
        )
        data = json.loads(raw_res)
        assert data["status"] == "error", f"Tool {tool_name} should fail in group"
        assert data["error_code"] == "GROUP_PRIVATE_ONLY"
        assert "private" in data["message"].lower()


@pytest.mark.asyncio
async def test_private_allowed_balance_tool(
    mock_service: AsyncMock, user_jid: JID, private_chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)
    mock_service.get_total_balance.return_value = {
        "total": Decimal("500000"),
        "accounts": [],
    }

    raw_res = await executor.execute(
        tool_name="finance_get_balance",
        arguments={},
        user_jid=user_jid,
        chat_jid=private_chat_jid,
    )
    data = json.loads(raw_res)
    assert data["status"] == "success"
    assert data["total_balance"] == 500000.0


@pytest.mark.asyncio
async def test_group_expense_strips_balance(
    mock_service: AsyncMock, user_jid: JID, group_chat_jid: JID
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
        id="tx-100",
        human_tx_id="TXN-001",
        owner_jid=str(user_jid),
        account_id=bca_acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        category_id=None,
        description="Makan siang",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service.add_expense.return_value = tx

    raw_res = await executor.execute(
        tool_name="finance_add_expense",
        arguments={"amount": 50000, "description": "Makan siang", "account_name": "BCA"},
        user_jid=user_jid,
        chat_jid=group_chat_jid,
    )
    data = json.loads(raw_res)
    assert data["status"] == "success"
    assert data["amount"] == 50000.0
    assert "new_balance" not in data
    assert "balance" not in data


@pytest.mark.asyncio
async def test_group_income_strips_balance(
    mock_service: AsyncMock, user_jid: JID, group_chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)

    bca_acc = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("1500000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_service.find_account_by_name.return_value = bca_acc
    mock_service._repo.get_account_by_id.return_value = bca_acc

    tx = FinanceTransaction(
        id="tx-101",
        human_tx_id="TXN-002",
        owner_jid=str(user_jid),
        account_id=bca_acc.id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("500000"),
        category_id=None,
        description="Gaji bonus",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service.add_income.return_value = tx

    raw_res = await executor.execute(
        tool_name="finance_add_income",
        arguments={"amount": 500000, "description": "Gaji bonus", "account_name": "BCA"},
        user_jid=user_jid,
        chat_jid=group_chat_jid,
    )
    data = json.loads(raw_res)
    assert data["status"] == "success"
    assert data["amount"] == 500000.0
    assert "new_balance" not in data
    assert "balance" not in data


@pytest.mark.asyncio
async def test_group_transfer_strips_balance(
    mock_service: AsyncMock, user_jid: JID, group_chat_jid: JID
) -> None:
    executor = FinanceToolExecutor(mock_service)

    bca = FinanceAccount(
        id="acc-bca",
        owner_jid=str(user_jid),
        name="BCA",
        account_type=AccountType.BANK,
        currency="IDR",
        balance=Decimal("900000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    gopay = FinanceAccount(
        id="acc-gopay",
        owner_jid=str(user_jid),
        name="GoPay",
        account_type=AccountType.EWALLET,
        currency="IDR",
        balance=Decimal("200000"),
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_service.find_account_by_name.side_effect = lambda _, name: bca if name == "BCA" else gopay
    mock_service._repo.get_account_by_id.side_effect = lambda acc_id, _: bca if acc_id == bca.id else gopay

    tx = FinanceTransaction(
        id="tx-102",
        human_tx_id="TXN-003",
        owner_jid=str(user_jid),
        account_id=bca.id,
        transaction_type=TransactionType.TRANSFER,
        amount=Decimal("100000"),
        category_id=None,
        description="Topup GoPay",
        transaction_date=datetime.now(UTC),
        transfer_to_account_id=gopay.id,
        created_at=datetime.now(UTC),
        account_name="BCA",
    )
    mock_service.transfer.return_value = tx

    raw_res = await executor.execute(
        tool_name="finance_transfer",
        arguments={"amount": 100000, "from_account_name": "BCA", "to_account_name": "GoPay"},
        user_jid=user_jid,
        chat_jid=group_chat_jid,
    )
    data = json.loads(raw_res)
    assert data["status"] == "success"
    assert data["amount"] == 100000.0
    assert "from_new_balance" not in data
    assert "to_new_balance" not in data
    assert "new_balance" not in data


def test_fast_path_group_vs_private():
    raw_res = json.dumps({
        "status": "success",
        "transaction": {
            "amount": 25000,
            "category_name": "Makanan",
            "account_name": "Kas",
            "description": "Siomay",
        },
        "new_balance": 500000,
    })

    # Private mode: includes balance
    res_private = try_finance_mutation_fast_path("finance_add_expense", raw_res, is_group=False)
    assert res_private is not None
    assert "Saldo Terkini" in res_private
    assert "Rp 500.000" in res_private

    # Group mode: excludes balance
    res_group = try_finance_mutation_fast_path("finance_add_expense", raw_res, is_group=True)
    assert res_group is not None
    assert "Pengeluaran Dicatat" in res_group
    assert "Rp 25.000" in res_group
    assert "Saldo Terkini" not in res_group
    assert "500.000" not in res_group


def test_fast_path_group_blocked_tool():
    raw_res = json.dumps({
        "status": "success",
        "total_balance": 1000000,
        "accounts": [],
    })
    res_group = try_finance_mutation_fast_path("finance_get_balance", raw_res, is_group=True)
    assert res_group is not None
    assert "private" in res_group.lower()


def test_context_policy_group_prompt():
    settings = Settings()

    policy_private = ContextPolicyManager.get_policy(
        intent="finance",
        text="catat makan 20rb",
        settings=settings,
        is_group=False,
    )
    assert policy_private.system_prompt == AI_FINANCE_SYSTEM_PROMPT

    policy_group = ContextPolicyManager.get_policy(
        intent="finance",
        text="catat makan 20rb",
        settings=settings,
        is_group=True,
    )
    assert policy_group.system_prompt == AI_FINANCE_GROUP_SYSTEM_PROMPT
