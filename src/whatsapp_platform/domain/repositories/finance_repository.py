"""IFinanceRepository — abstract interface for finance data access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from whatsapp_platform.domain.entities.finance import (
    BudgetProgress,
    CategorySummary,
    FinanceAccount,
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    MonthlySummary,
)


class IFinanceRepository(ABC):

    # ── Accounts ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_account(self, account: FinanceAccount) -> FinanceAccount: ...

    @abstractmethod
    async def get_accounts(self, owner_jid: str) -> list[FinanceAccount]: ...

    @abstractmethod
    async def get_account_by_id(self, account_id: str, owner_jid: str) -> FinanceAccount | None: ...

    @abstractmethod
    async def update_account_balance(self, account_id: str, new_balance: Decimal) -> None: ...

    @abstractmethod
    async def delete_account(self, account_id: str, owner_jid: str) -> bool: ...

    # ── Categories ────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_category(self, category: FinanceCategory) -> FinanceCategory: ...

    @abstractmethod
    async def get_categories(self, owner_jid: str) -> list[FinanceCategory]: ...

    @abstractmethod
    async def find_category_by_name(
        self, owner_jid: str, name: str
    ) -> FinanceCategory | None: ...

    # ── Transactions ──────────────────────────────────────────────────────────

    @abstractmethod
    async def add_transaction(self, transaction: FinanceTransaction) -> FinanceTransaction: ...

    @abstractmethod
    async def save_transaction_atomic(
        self, transaction: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def reverse_transaction_atomic(
        self, original_tx_id: str, owner_jid: str, reversal_tx: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def update_transaction_atomic(
        self, transaction: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def get_transaction_by_id(self, tx_id: str, owner_jid: str) -> FinanceTransaction | None: ...

    @abstractmethod
    async def get_transaction_by_idempotency_key(
        self, owner_jid: str, idempotency_key: str
    ) -> FinanceTransaction | None: ...

    @abstractmethod
    async def get_transactions(
        self,
        owner_jid: str,
        limit: int = 10,
        account_id: str | None = None,
        category_id: str | None = None,
        transaction_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[FinanceTransaction]: ...

    @abstractmethod
    async def search_transactions(
        self,
        owner_jid: str,
        keyword: str | None = None,
        date: datetime | None = None,
        transaction_type: str | None = None,
        limit: int = 5,
    ) -> list[FinanceTransaction]:
        """Cari transaksi berdasarkan keyword deskripsi dan/atau tanggal.
        Digunakan sebelum update/delete untuk resolve transaction_id."""
        ...

    @abstractmethod
    async def delete_transaction(
        self,
        tx_id: str,
        owner_jid: str,
    ) -> bool:
        """Hard delete transaksi dan kembalikan saldo ke kondisi sebelumnya.
        Mengembalikan True jika berhasil dihapus."""
        ...

    @abstractmethod
    async def get_transactions_by_period(
        self,
        owner_jid: str,
        start: datetime,
        end: datetime,
        account_id: str | None = None,
    ) -> list[FinanceTransaction]: ...

    @abstractmethod
    async def get_monthly_summary(
        self, owner_jid: str, year: int, month: int
    ) -> MonthlySummary: ...

    @abstractmethod
    async def get_category_summary(
        self, owner_jid: str, start: datetime, end: datetime
    ) -> list[CategorySummary]: ...

    # ── Budgets ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def upsert_budget(self, budget: FinanceBudget) -> FinanceBudget: ...

    @abstractmethod
    async def get_budget(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> FinanceBudget | None: ...

    @abstractmethod
    async def get_budgets(
        self, owner_jid: str, month: int, year: int
    ) -> list[FinanceBudget]: ...

    @abstractmethod
    async def delete_budget(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> bool: ...

    @abstractmethod
    async def get_budget_progress(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> BudgetProgress | None: ...

    @abstractmethod
    async def list_budgets_with_progress(
        self, owner_jid: str, month: int, year: int
    ) -> list[BudgetProgress]: ...

    # ── Reset ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def reset_all_data(self, owner_jid: str) -> dict[str, int]:
        """Hapus semua data finance milik owner_jid.

        Returns:
            dict berisi jumlah baris yang dihapus per tabel,
            contoh: {'transactions': 5, 'budgets': 2, 'accounts': 3, 'categories': 18}
        """
        ...

