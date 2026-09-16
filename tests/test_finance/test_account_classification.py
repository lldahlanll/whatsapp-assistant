"""Tests for Finance Part 1 — Account Classification."""

from __future__ import annotations

import json
from decimal import Decimal
import pytest

from whatsapp_platform.domain.entities.finance import (
    AVAILABLE_ACCOUNT_TYPES,
    INVESTMENT_ACCOUNT_TYPES,
    AccountType,
    FinanceAccount,
)
from whatsapp_platform.features.finance.formatter import format_accounts_list, format_balance
from whatsapp_platform.features.finance.service import FinanceService
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path
from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor


class InMemoryFinanceRepo:
    """In-memory repository for testing finance account classification and isolation."""

    def __init__(self) -> None:
        self.accounts: dict[str, list[FinanceAccount]] = {}
        self.categories: dict[str, list] = {}

    async def get_accounts(self, owner_jid: str) -> list[FinanceAccount]:
        return [a for a in self.accounts.get(owner_jid, []) if a.is_active]

    async def get_account_by_id(self, account_id: str, owner_jid: str) -> FinanceAccount | None:
        for a in self.accounts.get(owner_jid, []):
            if a.id == account_id:
                return a
        return None

    async def create_account(self, account: FinanceAccount) -> FinanceAccount:
        if account.owner_jid not in self.accounts:
            self.accounts[account.owner_jid] = []
        self.accounts[account.owner_jid].append(account)
        return account

    async def get_categories(self, owner_jid: str) -> list:
        return self.categories.get(owner_jid, [])

    async def create_category(self, cat) -> None:
        if cat.owner_jid not in self.categories:
            self.categories[cat.owner_jid] = []
        self.categories[cat.owner_jid].append(cat)


@pytest.fixture
def in_memory_repo() -> InMemoryFinanceRepo:
    return InMemoryFinanceRepo()


def test_account_type_enum_and_classification_properties():
    """Acceptance Criteria 1 & 7: deposit is a valid AccountType and classification is correct."""
    assert AccountType.DEPOSIT == "deposit"
    assert AccountType.DEPOSIT.value == "deposit"

    # All account types check
    all_types = {t.value for t in AccountType}
    assert all_types == {"cash", "bank", "ewallet", "savings", "deposit", "investment"}

    # Available vs Investment sets
    assert AccountType.CASH in AVAILABLE_ACCOUNT_TYPES
    assert AccountType.BANK in AVAILABLE_ACCOUNT_TYPES
    assert AccountType.EWALLET in AVAILABLE_ACCOUNT_TYPES
    assert AccountType.SAVINGS in AVAILABLE_ACCOUNT_TYPES

    assert AccountType.DEPOSIT in INVESTMENT_ACCOUNT_TYPES
    assert AccountType.INVESTMENT in INVESTMENT_ACCOUNT_TYPES

    # Properties
    assert AccountType.CASH.is_available is True
    assert AccountType.CASH.is_investment is False
    assert AccountType.CASH.classification == "available"

    assert AccountType.BANK.is_available is True
    assert AccountType.EWALLET.is_available is True
    assert AccountType.SAVINGS.is_available is True

    assert AccountType.DEPOSIT.is_available is False
    assert AccountType.DEPOSIT.is_investment is True
    assert AccountType.DEPOSIT.classification == "investment"

    assert AccountType.INVESTMENT.is_available is False
    assert AccountType.INVESTMENT.is_investment is True
    assert AccountType.INVESTMENT.classification == "investment"


def test_finance_account_classification_properties():
    """Verify FinanceAccount helper properties."""
    acc_bank = FinanceAccount(
        id="1", owner_jid="user@s.whatsapp.net", name="BCA",
        account_type=AccountType.BANK, currency="IDR",
        balance=Decimal("3766000"), is_active=True, created_at=None,  # type: ignore
    )
    acc_deposit = FinanceAccount(
        id="2", owner_jid="user@s.whatsapp.net", name="Neo Deposit",
        account_type=AccountType.DEPOSIT, currency="IDR",
        balance=Decimal("5600000"), is_active=True, created_at=None,  # type: ignore
    )

    assert acc_bank.is_available_balance is True
    assert acc_bank.is_investment is False
    assert acc_bank.classification == "available"

    assert acc_deposit.is_available_balance is False
    assert acc_deposit.is_investment is True
    assert acc_deposit.classification == "investment"


@pytest.mark.asyncio
async def test_get_total_balance_with_classification(in_memory_repo):
    """Verify service calculates total, available_balance, and investment_balance."""
    owner_jid = "user1@s.whatsapp.net"
    service = FinanceService(repo=in_memory_repo)

    # Buat akun sesuai contoh di task:
    # BCA = bank = Rp3.766.000
    # Neo Savings = savings = Rp5.558.000
    # Neo Deposit = deposit = Rp5.600.000
    # RDPU = investment = Rp3.357.000
    await service.create_account(owner_jid, "BCA", AccountType.BANK, Decimal("3766000"))
    await service.create_account(owner_jid, "Neo Savings", AccountType.SAVINGS, Decimal("5558000"))
    await service.create_account(owner_jid, "Neo Deposit", AccountType.DEPOSIT, Decimal("5600000"))
    await service.create_account(owner_jid, "RDPU", AccountType.INVESTMENT, Decimal("3357000"))

    data = await service.get_total_balance(owner_jid)

    # Saldo Tersedia: 3.766.000 + 5.558.000 = 9.324.000
    # Investasi: 5.600.000 + 3.357.000 = 8.957.000
    # Total Aset: 18.281.000
    assert data["available_balance"] == Decimal("9324000")
    assert data["investment_balance"] == Decimal("8957000")
    assert data["total"] == Decimal("18281000")

    # Pastikan classification ada di setiap item accounts
    classifications = {acc["name"]: acc["classification"] for acc in data["accounts"]}
    assert classifications["BCA"] == "available"
    assert classifications["Neo Savings"] == "available"
    assert classifications["Neo Deposit"] == "investment"
    assert classifications["RDPU"] == "investment"


@pytest.mark.asyncio
async def test_multi_user_isolation_and_dynamic_account_names(in_memory_repo):
    """Acceptance Criteria 2, 3, 4: User bebas memberi nama akun dan terisolasi antar user."""
    user1 = "alice@s.whatsapp.net"
    user2 = "bob@s.whatsapp.net"
    service = FinanceService(repo=in_memory_repo)

    # User 1 punya akun custom
    await service.create_account(user1, "Dompet Pribadi", AccountType.CASH, Decimal("150000"))
    await service.create_account(user1, "Deposito BPR", AccountType.DEPOSIT, Decimal("10000000"))

    # User 2 punya akun yang sama sekali berbeda
    await service.create_account(user2, "Tabungan Haji", AccountType.SAVINGS, Decimal("5000000"))
    await service.create_account(user2, "Saham BBCA", AccountType.INVESTMENT, Decimal("25000000"))

    u1_accounts = await service.get_accounts(user1)
    u2_accounts = await service.get_accounts(user2)

    assert [a.name for a in u1_accounts] == ["Dompet Pribadi", "Deposito BPR"]
    assert [a.name for a in u2_accounts] == ["Tabungan Haji", "Saham BBCA"]

    u1_bal = await service.get_total_balance(user1)
    assert u1_bal["available_balance"] == Decimal("150000")
    assert u1_bal["investment_balance"] == Decimal("10000000")
    assert u1_bal["total"] == Decimal("10150000")

    u2_bal = await service.get_total_balance(user2)
    assert u2_bal["available_balance"] == Decimal("5000000")
    assert u2_bal["investment_balance"] == Decimal("25000000")
    assert u2_bal["total"] == Decimal("30000000")


def test_format_balance_with_classification_report():
    """Verify format_balance produces grouped output as in prompt example."""
    data = {
        "total": Decimal("18281000"),
        "available_balance": Decimal("9324000"),
        "investment_balance": Decimal("8957000"),
        "currency": "IDR",
        "accounts": [
            {"name": "BCA", "type": "bank", "balance": Decimal("3766000"), "classification": "available"},
            {"name": "Neo Savings", "type": "savings", "balance": Decimal("5558000"), "classification": "available"},
            {"name": "Neo Deposit", "type": "deposit", "balance": Decimal("5600000"), "classification": "investment"},
            {"name": "RDPU", "type": "investment", "balance": Decimal("3357000"), "classification": "investment"},
        ],
    }
    text = format_balance(data)

    assert "Saldo Tersedia:" in text
    assert "• *BCA*: Rp 3.766.000" in text
    assert "• *Neo Savings*: Rp 5.558.000" in text
    assert "Investasi:" in text
    assert "• *Neo Deposit*: Rp 5.600.000" in text
    assert "• *RDPU*: Rp 3.357.000" in text
    assert "Total Aset: Rp 18.281.000" in text


def test_format_accounts_list_with_classification():
    """Verify format_accounts_list groups and shows account types."""
    accounts = [
        FinanceAccount("1", "u", "BCA", AccountType.BANK, "IDR", Decimal("3766000"), True, None),  # type: ignore
        FinanceAccount("2", "u", "Neo Deposit", AccountType.DEPOSIT, "IDR", Decimal("5600000"), True, None),  # type: ignore
    ]
    text = format_accounts_list(accounts)
    assert "Saldo Tersedia:" in text
    assert "BCA" in text
    assert "bank" in text
    assert "Investasi:" in text
    assert "Neo Deposit" in text
    assert "deposit" in text


def test_fast_path_balance_with_deposit_and_investment():
    """Verify fast path displays grouped classification when deposit/investment exists."""
    raw_res = json.dumps({
        "status": "success",
        "accounts": [
            {"name": "BCA", "type": "bank", "balance": 3766000, "classification": "available"},
            {"name": "Neo Savings", "type": "savings", "balance": 5558000, "classification": "available"},
            {"name": "Neo Deposit", "type": "deposit", "balance": 5600000, "classification": "investment"},
            {"name": "RDPU", "type": "investment", "balance": 3357000, "classification": "investment"},
        ]
    })
    result = try_finance_mutation_fast_path("finance_get_balance", raw_res)
    assert result is not None
    assert "Saldo Rekening" in result
    assert "Saldo Tersedia:" in result
    assert "BCA" in result
    assert "Rp 3.766.000" in result
    assert "Investasi:" in result
    assert "Neo Deposit" in result
    assert "Rp 5.600.000" in result
    assert "Total Aset: Rp 18.281.000" in result


@pytest.mark.asyncio
async def test_tool_executor_create_deposit_account(in_memory_repo):
    """Verify tool_executor handles deposit and deposito aliases."""
    from whatsapp_platform.domain.value_objects.jid import JID

    service = FinanceService(repo=in_memory_repo)
    executor = FinanceToolExecutor(finance_service=service)
    jid = JID.parse("user1@s.whatsapp.net")

    # Test "deposit"
    res1 = await executor.execute(
        tool_name="finance_create_account",
        arguments={"name": "Neo Deposit 6 Bulan", "account_type": "deposit", "initial_balance": 5000000},
        user_jid=jid,
        chat_jid=jid,
    )
    data1 = json.loads(res1)
    assert data1["status"] == "success"
    assert data1["account_type"] == "deposit"

    # Test alias "deposito"
    res2 = await executor.execute(
        tool_name="finance_create_account",
        arguments={"name": "Deposito Mandiri", "account_type": "deposito", "initial_balance": 10000000},
        user_jid=jid,
        chat_jid=jid,
    )
    data2 = json.loads(res2)
    assert data2["status"] == "success"
    assert data2["account_type"] == "deposit"
