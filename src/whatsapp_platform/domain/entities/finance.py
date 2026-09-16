"""Domain entities for personal finance feature."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class AccountType(str, Enum):
    CASH = "cash"
    BANK = "bank"
    EWALLET = "ewallet"
    SAVINGS = "savings"
    DEPOSIT = "deposit"
    INVESTMENT = "investment"

    @property
    def is_available(self) -> bool:
        return self in AVAILABLE_ACCOUNT_TYPES

    @property
    def is_investment(self) -> bool:
        return self in INVESTMENT_ACCOUNT_TYPES

    @property
    def classification(self) -> str:
        return "available" if self.is_available else "investment"


AVAILABLE_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.CASH,
    AccountType.BANK,
    AccountType.EWALLET,
    AccountType.SAVINGS,
})

INVESTMENT_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.DEPOSIT,
    AccountType.INVESTMENT,
})


class CategoryType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


@dataclass
class FinanceAccount:
    id: str
    owner_jid: str
    name: str
    account_type: AccountType
    currency: str
    balance: Decimal
    is_active: bool
    created_at: datetime

    @property
    def is_available_balance(self) -> bool:
        return self.account_type.is_available

    @property
    def is_investment(self) -> bool:
        return self.account_type.is_investment

    @property
    def classification(self) -> str:
        return self.account_type.classification


@dataclass
class FinanceCategory:
    id: str
    owner_jid: str
    name: str
    category_type: CategoryType
    icon: str | None
    is_default: bool
    created_at: datetime


@dataclass
class FinanceTransaction:
    id: str
    owner_jid: str
    account_id: str
    transaction_type: TransactionType
    amount: Decimal
    category_id: str | None
    description: str | None
    transaction_date: datetime
    transfer_to_account_id: str | None
    created_at: datetime
    human_tx_id: str | None = field(default=None)
    idempotency_key: str | None = field(default=None)
    is_reversed: bool = field(default=False)
    reversal_of_id: str | None = field(default=None)
    account_name: str | None = field(default=None)
    category_name: str | None = field(default=None)
    category_icon: str | None = field(default=None)
    transfer_to_account_name: str | None = field(default=None)


@dataclass
class MonthlySummary:
    year: int
    month: int
    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    top_expense_categories: list[CategorySummary] = field(default_factory=list)


@dataclass
class CategorySummary:
    category_name: str
    category_icon: str | None
    total: Decimal
    transaction_count: int


@dataclass
class FinanceBudget:
    id: str
    owner_jid: str
    category_id: str
    amount: Decimal
    month: int
    year: int
    created_at: datetime
    updated_at: datetime
    category_name: str | None = field(default=None)
    category_icon: str | None = field(default=None)


@dataclass
class BudgetProgress:
    budget: FinanceBudget
    spent: Decimal
    remaining: Decimal
    percentage: float
    status: str
