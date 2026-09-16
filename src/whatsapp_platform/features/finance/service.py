"""FinanceService — business logic layer for personal finance tracking."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    BudgetProgress,
    FinanceAccount,
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    MonthlySummary,
    TransactionType,
)
from whatsapp_platform.features.finance.default_categories import (
    ALL_DEFAULT_CATEGORIES,
    EXPENSE_KEYWORD_MAP,
    INCOME_KEYWORD_MAP,
)
from whatsapp_platform.features.finance.parser import (
    guess_category_from_text,
    parse_amount_from_text,
    parse_description_without_amount,
)

if TYPE_CHECKING:
    from whatsapp_platform.domain.repositories.finance_repository import IFinanceRepository

logger = structlog.get_logger()


class FinanceServiceError(Exception):
    pass


class AccountNotFoundError(FinanceServiceError):
    pass


class AccountRequiredError(FinanceServiceError):
    pass


class InsufficientBalanceError(FinanceServiceError):
    pass


class DuplicateTransactionError(FinanceServiceError):
    pass


class InvalidAmountError(FinanceServiceError):
    pass


class TransactionNotFoundError(FinanceServiceError):
    pass


class TransactionAlreadyReversedError(FinanceServiceError):
    pass


class CategoryNotFoundError(FinanceServiceError):
    pass


class BudgetNotFoundError(FinanceServiceError):
    pass



def _generate_human_tx_id() -> str:
    now = datetime.now(UTC)
    return f"TXN-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


class FinanceService:
    def __init__(self, repo: IFinanceRepository) -> None:
        self._repo = repo

    # ── Setup ─────────────────────────────────────────────────────────────────

    async def ensure_defaults(self, owner_jid: str) -> None:
        """Create default categories if user has none yet."""
        categories = await self._repo.get_categories(owner_jid)
        if not categories:
            for cat in ALL_DEFAULT_CATEGORIES:
                await self._repo.create_category(
                    FinanceCategory(
                        id=str(uuid.uuid4()),
                        owner_jid=owner_jid,
                        name=cat["name"],
                        category_type=cat["type"],
                        icon=cat["icon"],
                        is_default=True,
                        created_at=datetime.now(UTC),
                    )
                )
            logger.info("Seeded default categories", owner=owner_jid)

    # ── Accounts ──────────────────────────────────────────────────────────────

    async def create_account(
        self,
        owner_jid: str,
        name: str,
        account_type: AccountType = AccountType.CASH,
        initial_balance: Decimal = Decimal("0"),
        currency: str = "IDR",
    ) -> FinanceAccount:
        account = FinanceAccount(
            id=str(uuid.uuid4()),
            owner_jid=owner_jid,
            name=name,
            account_type=account_type,
            currency=currency,
            balance=initial_balance,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        return await self._repo.create_account(account)

    async def get_accounts(self, owner_jid: str) -> list[FinanceAccount]:
        await self.ensure_defaults(owner_jid)
        return await self._repo.get_accounts(owner_jid)

    async def get_categories(
        self, owner_jid: str, category_type: str | None = None
    ) -> list[FinanceCategory]:
        """Ambil kategori yang tersedia. Pastikan defaults sudah di-seed."""
        await self.ensure_defaults(owner_jid)
        categories = await self._repo.get_categories(owner_jid)
        if category_type:
            ct = category_type.lower()
            categories = [c for c in categories if c.category_type.value == ct]
        return categories

    async def get_total_balance(self, owner_jid: str) -> dict:
        accounts = await self.get_accounts(owner_jid)
        total = sum(a.balance for a in accounts)
        available_balance = sum(a.balance for a in accounts if a.is_available_balance)
        investment_balance = sum(a.balance for a in accounts if a.is_investment)
        return {
            "total": total,
            "available_balance": available_balance,
            "investment_balance": investment_balance,
            "currency": "IDR",
            "accounts": [
                {
                    "id": a.id,
                    "name": a.name,
                    "balance": a.balance,
                    "type": a.account_type.value,
                    "classification": a.classification,
                }
                for a in accounts
            ],
        }

    async def _resolve_account(
        self, owner_jid: str, account_id: str | None
    ) -> FinanceAccount:
        if account_id:
            acc = await self._repo.get_account_by_id(account_id, owner_jid)
            if not acc:
                raise AccountNotFoundError(f"Rekening '{account_id}' tidak ditemukan.")
            return acc

        accounts = await self.get_accounts(owner_jid)
        if not accounts:
            raise AccountNotFoundError(
                "Belum ada rekening/dompet terdaftar. Silakan buat rekening terlebih dahulu "
                "(contoh: 'buat rekening BCA saldo awal 1jt' atau '!finance rekening baru BCA bank 1jt')."
            )
        if len(accounts) == 1:
            return accounts[0]

        acc_names = ", ".join(f"'{a.name}'" for a in accounts)
        raise AccountRequiredError(
            f"Rekening/dompet belum ditentukan. Silakan sebutkan rekening yang digunakan ({acc_names})."
        )

    async def find_account_by_name(
        self, owner_jid: str, name: str
    ) -> FinanceAccount | None:
        accounts = await self.get_accounts(owner_jid)
        name_lower = name.lower()
        for acc in accounts:
            if (
                acc.name.lower() == name_lower
                or name_lower in acc.name.lower()
                or acc.name.lower() in name_lower
            ):
                return acc
        return None

    async def delete_account(
        self, owner_jid: str, name_or_id: str
    ) -> FinanceAccount:
        """Menonaktifkan / menghapus rekening berdasarkan ID atau nama."""
        acc = await self._repo.get_account_by_id(name_or_id, owner_jid)
        if not acc:
            acc = await self.find_account_by_name(owner_jid, name_or_id)

        if not acc:
            raise AccountNotFoundError(f"Rekening '{name_or_id}' tidak ditemukan.")

        success = await self._repo.delete_account(acc.id, owner_jid)
        if not success:
            raise FinanceServiceError(f"Gagal menghapus rekening '{acc.name}'.")

        logger.info("Account deleted/deactivated", owner=owner_jid, account_id=acc.id, name=acc.name)
        return acc

    # ── Categories ────────────────────────────────────────────────────────────

    async def _resolve_category(
        self, owner_jid: str, category_name: str | None, tx_type: TransactionType
    ) -> FinanceCategory | None:
        await self.ensure_defaults(owner_jid)

        if category_name:
            cat = await self._repo.find_category_by_name(owner_jid, category_name)
            if cat:
                return cat

        return None

    async def _auto_category(
        self, owner_jid: str, text: str, tx_type: TransactionType
    ) -> FinanceCategory | None:
        keyword_map = (
            EXPENSE_KEYWORD_MAP if tx_type == TransactionType.EXPENSE else INCOME_KEYWORD_MAP
        )
        guessed_name = guess_category_from_text(text, keyword_map)
        if guessed_name:
            return await self._repo.find_category_by_name(owner_jid, guessed_name)
        return None

    # ── Income ────────────────────────────────────────────────────────────────

    async def add_income(
        self,
        owner_jid: str,
        amount: Decimal,
        description: str | None = None,
        category_name: str | None = None,
        account_id: str | None = None,
        date: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> FinanceTransaction:
        if amount <= 0:
            raise InvalidAmountError("Jumlah pemasukan harus lebih dari 0.")

        if idempotency_key:
            existing = await self._repo.get_transaction_by_idempotency_key(owner_jid, idempotency_key)
            if existing:
                logger.info("Duplicate transaction prevented via idempotency key", key=idempotency_key)
                return existing

        await self.ensure_defaults(owner_jid)
        account = await self._resolve_account(owner_jid, account_id)
        category = await self._resolve_category(owner_jid, category_name, TransactionType.INCOME)
        if not category and description:
            category = await self._auto_category(owner_jid, description, TransactionType.INCOME)

        tx = FinanceTransaction(
            id=str(uuid.uuid4()),
            human_tx_id=_generate_human_tx_id(),
            idempotency_key=idempotency_key,
            owner_jid=owner_jid,
            account_id=account.id,
            transaction_type=TransactionType.INCOME,
            amount=amount,
            category_id=category.id if category else None,
            description=description,
            transaction_date=date or datetime.now(UTC),
            transfer_to_account_id=None,
            is_reversed=False,
            reversal_of_id=None,
            created_at=datetime.now(UTC),
            account_name=account.name,
            category_name=category.name if category else None,
            category_icon=category.icon if category else None,
        )

        new_balance = account.balance + amount
        saved_tx = await self._repo.save_transaction_atomic(tx, {account.id: new_balance})
        if saved_tx.account_name is None:
            saved_tx.account_name = account.name
        if saved_tx.category_name is None and category:
            saved_tx.category_name = category.name
            saved_tx.category_icon = category.icon
        logger.info("Income added atomically", owner=owner_jid, amount=str(amount), account=account.name)
        return saved_tx

    # ── Expense ───────────────────────────────────────────────────────────────

    async def add_expense(
        self,
        owner_jid: str,
        amount: Decimal,
        description: str | None = None,
        category_name: str | None = None,
        account_id: str | None = None,
        date: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> FinanceTransaction:
        if amount <= 0:
            raise InvalidAmountError("Jumlah pengeluaran harus lebih dari 0.")

        if idempotency_key:
            existing = await self._repo.get_transaction_by_idempotency_key(owner_jid, idempotency_key)
            if existing:
                logger.info("Duplicate transaction prevented via idempotency key", key=idempotency_key)
                return existing

        await self.ensure_defaults(owner_jid)
        account = await self._resolve_account(owner_jid, account_id)

        if account.balance < amount:
            shortfall = amount - account.balance
            raise InsufficientBalanceError(
                f"Saldo {account.name} Rp {account.balance:,.0f}, sedangkan transaksi Rp {amount:,.0f}. Kurang Rp {shortfall:,.0f}."
            )

        category = await self._resolve_category(owner_jid, category_name, TransactionType.EXPENSE)
        if not category and description:
            category = await self._auto_category(owner_jid, description, TransactionType.EXPENSE)

        tx = FinanceTransaction(
            id=str(uuid.uuid4()),
            human_tx_id=_generate_human_tx_id(),
            idempotency_key=idempotency_key,
            owner_jid=owner_jid,
            account_id=account.id,
            transaction_type=TransactionType.EXPENSE,
            amount=amount,
            category_id=category.id if category else None,
            description=description,
            transaction_date=date or datetime.now(UTC),
            transfer_to_account_id=None,
            is_reversed=False,
            reversal_of_id=None,
            created_at=datetime.now(UTC),
            account_name=account.name,
            category_name=category.name if category else None,
            category_icon=category.icon if category else None,
        )

        new_balance = account.balance - amount
        saved_tx = await self._repo.save_transaction_atomic(tx, {account.id: new_balance})
        if saved_tx.account_name is None:
            saved_tx.account_name = account.name
        if saved_tx.category_name is None and category:
            saved_tx.category_name = category.name
            saved_tx.category_icon = category.icon
        logger.info("Expense added atomically", owner=owner_jid, amount=str(amount), account=account.name)
        return saved_tx

    # ── Transfer ──────────────────────────────────────────────────────────────

    async def transfer(
        self,
        owner_jid: str,
        amount: Decimal,
        from_account_id: str,
        to_account_id: str,
        description: str | None = None,
        date: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> FinanceTransaction:
        if amount <= 0:
            raise InvalidAmountError("Jumlah transfer harus lebih dari 0.")

        if idempotency_key:
            existing = await self._repo.get_transaction_by_idempotency_key(owner_jid, idempotency_key)
            if existing:
                logger.info("Duplicate transfer prevented via idempotency key", key=idempotency_key)
                return existing

        from_acc = await self._repo.get_account_by_id(from_account_id, owner_jid)
        to_acc = await self._repo.get_account_by_id(to_account_id, owner_jid)

        if not from_acc:
            raise AccountNotFoundError("Rekening asal tidak ditemukan.")
        if not to_acc:
            raise AccountNotFoundError("Rekening tujuan tidak ditemukan.")
        if from_acc.id == to_acc.id:
            raise FinanceServiceError("Rekening asal dan tujuan tidak boleh sama.")

        if from_acc.balance < amount:
            shortfall = amount - from_acc.balance
            raise InsufficientBalanceError(
                f"Saldo {from_acc.name} Rp {from_acc.balance:,.0f}, sedangkan transaksi Rp {amount:,.0f}. Kurang Rp {shortfall:,.0f}."
            )

        tx = FinanceTransaction(
            id=str(uuid.uuid4()),
            human_tx_id=_generate_human_tx_id(),
            idempotency_key=idempotency_key,
            owner_jid=owner_jid,
            account_id=from_acc.id,
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            category_id=None,
            description=description or f"Transfer ke {to_acc.name}",
            transaction_date=date or datetime.now(UTC),
            transfer_to_account_id=to_acc.id,
            is_reversed=False,
            reversal_of_id=None,
            created_at=datetime.now(UTC),
            account_name=from_acc.name,
            transfer_to_account_name=to_acc.name,
        )

        balance_updates = {
            from_acc.id: from_acc.balance - amount,
            to_acc.id: to_acc.balance + amount,
        }
        saved_tx = await self._repo.save_transaction_atomic(tx, balance_updates)
        if saved_tx.account_name is None:
            saved_tx.account_name = from_acc.name
        if saved_tx.transfer_to_account_name is None:
            saved_tx.transfer_to_account_name = to_acc.name
        logger.info(
            "Transfer recorded atomically",
            owner=owner_jid,
            amount=str(amount),
            from_account=from_acc.name,
            to_account=to_acc.name,
        )
        return saved_tx

    # ── Reversal & Correction ─────────────────────────────────────────────────

    async def reverse_transaction(
        self,
        owner_jid: str,
        tx_id_or_human_id: str,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> FinanceTransaction:
        orig_tx = await self._repo.get_transaction_by_id(tx_id_or_human_id, owner_jid)
        if not orig_tx:
            raise TransactionNotFoundError(f"Transaksi '{tx_id_or_human_id}' tidak ditemukan.")
        if orig_tx.is_reversed:
            raise TransactionAlreadyReversedError(f"Transaksi '{tx_id_or_human_id}' sudah pernah di-reverse.")

        from_acc = await self._repo.get_account_by_id(orig_tx.account_id, owner_jid)
        if not from_acc:
            raise AccountNotFoundError("Rekening transaksi tidak ditemukan.")

        balance_updates: dict[str, Decimal] = {}
        if orig_tx.transaction_type == TransactionType.INCOME:
            if from_acc.balance < orig_tx.amount:
                raise InsufficientBalanceError(
                    f"Saldo {from_acc.name} ({from_acc.balance:,.0f}) tidak mencukupi untuk reversal pemasukan."
                )
            balance_updates[from_acc.id] = from_acc.balance - orig_tx.amount
        elif orig_tx.transaction_type == TransactionType.EXPENSE:
            balance_updates[from_acc.id] = from_acc.balance + orig_tx.amount
        elif orig_tx.transaction_type == TransactionType.TRANSFER:
            if not orig_tx.transfer_to_account_id:
                raise FinanceServiceError("Transaksi transfer tidak memiliki rekening tujuan.")
            to_acc = await self._repo.get_account_by_id(orig_tx.transfer_to_account_id, owner_jid)
            if not to_acc:
                raise AccountNotFoundError("Rekening tujuan transfer tidak ditemukan.")
            if to_acc.balance < orig_tx.amount:
                raise InsufficientBalanceError(
                    f"Saldo {to_acc.name} ({to_acc.balance:,.0f}) tidak mencukupi untuk membatalkan transfer."
                )
            balance_updates[from_acc.id] = from_acc.balance + orig_tx.amount
            balance_updates[to_acc.id] = to_acc.balance - orig_tx.amount

        rev_tx = FinanceTransaction(
            id=str(uuid.uuid4()),
            human_tx_id=_generate_human_tx_id(),
            idempotency_key=idempotency_key,
            owner_jid=owner_jid,
            account_id=orig_tx.account_id,
            transaction_type=orig_tx.transaction_type,
            amount=orig_tx.amount,
            category_id=orig_tx.category_id,
            description=reason or f"Reversal of {orig_tx.human_tx_id or orig_tx.id}",
            transaction_date=datetime.now(UTC),
            transfer_to_account_id=orig_tx.transfer_to_account_id,
            is_reversed=False,
            reversal_of_id=orig_tx.id,
            created_at=datetime.now(UTC),
        )

        saved_rev = await self._repo.reverse_transaction_atomic(
            original_tx_id=orig_tx.id,
            owner_jid=owner_jid,
            reversal_tx=rev_tx,
            balance_updates=balance_updates,
        )
        logger.info("Transaction reversed atomically", owner=owner_jid, orig_id=orig_tx.id)
        return saved_rev

    async def correct_transaction(
        self,
        owner_jid: str,
        original_tx_id: str,
        new_amount: Decimal,
        new_description: str | None = None,
        new_category_name: str | None = None,
        new_account_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> FinanceTransaction:
        if new_amount <= 0:
            raise InvalidAmountError("Jumlah transaksi harus lebih dari 0.")

        orig_tx = await self._repo.get_transaction_by_id(original_tx_id, owner_jid)
        if not orig_tx:
            raise TransactionNotFoundError(f"Transaksi '{original_tx_id}' tidak ditemukan.")
        if orig_tx.is_reversed:
            raise TransactionAlreadyReversedError(
                f"Transaksi '{orig_tx.human_tx_id or orig_tx.id}' sudah di-reverse dan tidak dapat diubah."
            )

        # 1. Resolve Account
        target_account_id = new_account_id or orig_tx.account_id
        target_acc = await self._repo.get_account_by_id(target_account_id, owner_jid)
        if not target_acc:
            raise AccountNotFoundError("Rekening transaksi tidak ditemukan.")

        orig_acc = (
            target_acc
            if target_account_id == orig_tx.account_id
            else await self._repo.get_account_by_id(orig_tx.account_id, owner_jid)
        )
        if not orig_acc:
            raise AccountNotFoundError("Rekening transaksi asal tidak ditemukan.")

        # 2. Resolve Category
        target_category_id = orig_tx.category_id
        target_category_name = orig_tx.category_name
        target_category_icon = orig_tx.category_icon

        if new_category_name:
            cat = await self._resolve_category(owner_jid, new_category_name, orig_tx.transaction_type)
            if cat:
                target_category_id = cat.id
                target_category_name = cat.name
                target_category_icon = cat.icon
        elif new_description and not target_category_id:
            cat = await self._auto_category(owner_jid, new_description, orig_tx.transaction_type)
            if cat:
                target_category_id = cat.id
                target_category_name = cat.name
                target_category_icon = cat.icon

        # 3. Calculate Balance Updates
        balance_updates: dict[str, Decimal] = {}
        old_amount = orig_tx.amount

        if orig_tx.transaction_type == TransactionType.EXPENSE:
            if target_account_id == orig_tx.account_id:
                # Same account: delta = old_amount - new_amount
                # New balance = current_balance + old_amount - new_amount
                adj = old_amount - new_amount
                new_bal = orig_acc.balance + adj
                if new_bal < 0:
                    shortfall = abs(new_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {orig_acc.name} tidak mencukupi untuk update nominal. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[orig_acc.id] = new_bal
            else:
                # Different accounts:
                balance_updates[orig_acc.id] = orig_acc.balance + old_amount
                if target_acc.balance < new_amount:
                    shortfall = new_amount - target_acc.balance
                    raise InsufficientBalanceError(
                        f"Saldo {target_acc.name} Rp {target_acc.balance:,.0f}, sedangkan transaksi Rp {new_amount:,.0f}. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[target_acc.id] = target_acc.balance - new_amount

        elif orig_tx.transaction_type == TransactionType.INCOME:
            if target_account_id == orig_tx.account_id:
                new_bal = orig_acc.balance - old_amount + new_amount
                if new_bal < 0:
                    shortfall = abs(new_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {orig_acc.name} tidak mencukupi untuk penyesuaian pemasukan. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[orig_acc.id] = new_bal
            else:
                new_orig_bal = orig_acc.balance - old_amount
                if new_orig_bal < 0:
                    shortfall = abs(new_orig_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {orig_acc.name} tidak mencukupi untuk memindahkan pemasukan. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[orig_acc.id] = new_orig_bal
                balance_updates[target_acc.id] = target_acc.balance + new_amount

        elif orig_tx.transaction_type == TransactionType.TRANSFER:
            to_acc_id = orig_tx.transfer_to_account_id
            if not to_acc_id:
                raise FinanceServiceError("Transaksi transfer tidak memiliki rekening tujuan.")
            to_acc = await self._repo.get_account_by_id(to_acc_id, owner_jid)
            if not to_acc:
                raise AccountNotFoundError("Rekening tujuan transfer tidak ditemukan.")

            if target_account_id == orig_tx.account_id:
                from_bal = orig_acc.balance + old_amount - new_amount
                if from_bal < 0:
                    shortfall = abs(from_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {orig_acc.name} tidak mencukupi untuk update transfer. Kurang Rp {shortfall:,.0f}."
                    )
                to_bal = to_acc.balance - old_amount + new_amount
                if to_bal < 0:
                    shortfall = abs(to_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {to_acc.name} tidak mencukupi untuk penyesuaian transfer. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[orig_acc.id] = from_bal
                balance_updates[to_acc.id] = to_bal
            else:
                from_orig_bal = orig_acc.balance + old_amount
                to_bal = to_acc.balance - old_amount + new_amount
                if to_bal < 0:
                    shortfall = abs(to_bal)
                    raise InsufficientBalanceError(
                        f"Saldo {to_acc.name} tidak mencukupi untuk penyesuaian transfer. Kurang Rp {shortfall:,.0f}."
                    )
                if target_acc.balance < new_amount:
                    shortfall = new_amount - target_acc.balance
                    raise InsufficientBalanceError(
                        f"Saldo {target_acc.name} tidak mencukupi untuk transfer. Kurang Rp {shortfall:,.0f}."
                    )
                balance_updates[orig_acc.id] = from_orig_bal
                balance_updates[target_acc.id] = target_acc.balance - new_amount
                balance_updates[to_acc.id] = to_bal

        # 4. Construct updated FinanceTransaction
        updated_tx = FinanceTransaction(
            id=orig_tx.id,
            human_tx_id=orig_tx.human_tx_id,
            idempotency_key=idempotency_key or orig_tx.idempotency_key,
            owner_jid=orig_tx.owner_jid,
            account_id=target_acc.id,
            transaction_type=orig_tx.transaction_type,
            amount=new_amount,
            category_id=target_category_id,
            description=new_description if new_description is not None else orig_tx.description,
            transaction_date=orig_tx.transaction_date,
            transfer_to_account_id=orig_tx.transfer_to_account_id,
            is_reversed=False,
            reversal_of_id=orig_tx.reversal_of_id,
            created_at=orig_tx.created_at,
            account_name=target_acc.name,
            category_name=target_category_name,
            category_icon=target_category_icon,
            transfer_to_account_name=orig_tx.transfer_to_account_name,
        )

        saved = await self._repo.update_transaction_atomic(
            transaction=updated_tx,
            balance_updates=balance_updates,
        )
        logger.info(
            "Transaction updated atomically",
            owner=owner_jid,
            tx_id=orig_tx.id,
            old_amount=str(old_amount),
            new_amount=str(new_amount),
        )
        return saved

    # Alias update_transaction -> correct_transaction
    update_transaction = correct_transaction

    # ── Reports ───────────────────────────────────────────────────────────────

    async def get_monthly_report(
        self, owner_jid: str, year: int | None = None, month: int | None = None
    ) -> MonthlySummary:
        now = datetime.now(UTC)
        return await self._repo.get_monthly_summary(
            owner_jid,
            year=year or now.year,
            month=month or now.month,
        )

    async def get_recent_transactions(
        self,
        owner_jid: str,
        limit: int = 10,
        account_id: str | None = None,
        transaction_type: str | None = None,
        date_from=None,
        date_to=None,
        category_id: str | None = None,
    ) -> list[FinanceTransaction]:
        return await self._repo.get_transactions(
            owner_jid,
            limit=limit,
            account_id=account_id,
            transaction_type=transaction_type,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
        )

    async def search_transactions(
        self,
        owner_jid: str,
        keyword: str | None = None,
        date=None,
        transaction_type: str | None = None,
        limit: int = 5,
    ) -> list[FinanceTransaction]:
        """Cari transaksi berdasarkan keyword deskripsi. Digunakan sebelum update/delete."""
        return await self._repo.search_transactions(
            owner_jid,
            keyword=keyword,
            date=date,
            transaction_type=transaction_type,
            limit=limit,
        )

    async def delete_transaction(
        self,
        owner_jid: str,
        tx_id_or_human_id: str,
    ) -> bool:
        """Hard delete transaksi dan kembalikan saldo ke kondisi sebelumnya."""
        # Pastikan transaksi ada dulu
        tx = await self._repo.get_transaction_by_id(tx_id_or_human_id, owner_jid)
        if not tx:
            raise TransactionNotFoundError(f"Transaksi '{tx_id_or_human_id}' tidak ditemukan.")
        if tx.is_reversed:
            raise TransactionAlreadyReversedError(
                f"Transaksi '{tx_id_or_human_id}' sudah di-reverse dan tidak dapat dihapus."
            )
        success = await self._repo.delete_transaction(tx.id, owner_jid)
        if success:
            logger.info("Transaction hard-deleted", owner=owner_jid, tx_id=tx.id)
        return success

    async def get_expense_summary(
        self, owner_jid: str, year: int | None = None, month: int | None = None
    ) -> list:
        from datetime import datetime as dt

        now = dt.now(UTC)
        y = year or now.year
        m = month or now.month
        start = datetime(y, m, 1, tzinfo=UTC)
        if m == 12:
            end = datetime(y + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(y, m + 1, 1, tzinfo=UTC)

        return await self._repo.get_category_summary(owner_jid, start, end)

    # ── Quick parser shorthand ────────────────────────────────────────────────

    def parse_amount(self, text: str) -> Decimal | None:
        return parse_amount_from_text(text)

    def parse_description(self, text: str) -> str:
        return parse_description_without_amount(text)

    # ── Budgets ───────────────────────────────────────────────────────────────

    async def resolve_expense_category(
        self, owner_jid: str, category_name: str
    ) -> FinanceCategory:
        await self.ensure_defaults(owner_jid)
        categories = await self._repo.get_categories(owner_jid)
        name_clean = category_name.strip().lower()

        # 1. Exact match (case-insensitive)
        for c in categories:
            if c.name.lower() == name_clean:
                return c

        # 2. Substring match
        for c in categories:
            if name_clean in c.name.lower() or c.name.lower() in name_clean:
                return c

        # 3. Guess by keyword map
        guessed = guess_category_from_text(name_clean, EXPENSE_KEYWORD_MAP)
        if guessed:
            for c in categories:
                if c.name.lower() == guessed.lower():
                    return c

        raise CategoryNotFoundError(f"Kategori '{category_name}' tidak ditemukan.")

    async def set_budget(
        self,
        owner_jid: str,
        category_name: str,
        amount: Decimal,
        month: int | None = None,
        year: int | None = None,
    ) -> BudgetProgress:
        if amount <= 0:
            raise InvalidAmountError("Jumlah budget harus lebih dari 0.")

        now = datetime.now(UTC)
        m = month if month is not None else now.month
        y = year if year is not None else now.year

        if not (1 <= m <= 12):
            raise FinanceServiceError(f"Bulan '{m}' tidak valid. Harus bernilai 1-12.")
        if y < 2000 or y > 2100:
            raise FinanceServiceError(f"Tahun '{y}' tidak valid.")

        category = await self.resolve_expense_category(owner_jid, category_name)

        budget = FinanceBudget(
            id=str(uuid.uuid4()),
            owner_jid=owner_jid,
            category_id=category.id,
            amount=amount,
            month=m,
            year=y,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            category_name=category.name,
            category_icon=category.icon,
        )
        await self._repo.upsert_budget(budget)
        progress = await self._repo.get_budget_progress(owner_jid, category.id, m, y)
        if not progress:
            progress = BudgetProgress(
                budget=budget,
                spent=Decimal("0"),
                remaining=amount,
                percentage=0.0,
                status="aman",
            )
        logger.info("Budget set", owner=owner_jid, category=category.name, amount=str(amount), month=m, year=y)
        return progress

    async def get_budget_progress(
        self,
        owner_jid: str,
        category_name: str,
        month: int | None = None,
        year: int | None = None,
    ) -> BudgetProgress | None:
        now = datetime.now(UTC)
        m = month if month is not None else now.month
        y = year if year is not None else now.year

        if not (1 <= m <= 12):
            raise FinanceServiceError(f"Bulan '{m}' tidak valid. Harus bernilai 1-12.")
        if y < 2000 or y > 2100:
            raise FinanceServiceError(f"Tahun '{y}' tidak valid.")

        category = await self.resolve_expense_category(owner_jid, category_name)
        return await self._repo.get_budget_progress(owner_jid, category.id, m, y)

    async def list_budgets(
        self,
        owner_jid: str,
        month: int | None = None,
        year: int | None = None,
    ) -> list[BudgetProgress]:
        await self.ensure_defaults(owner_jid)
        now = datetime.now(UTC)
        m = month if month is not None else now.month
        y = year if year is not None else now.year

        if not (1 <= m <= 12):
            raise FinanceServiceError(f"Bulan '{m}' tidak valid. Harus bernilai 1-12.")
        if y < 2000 or y > 2100:
            raise FinanceServiceError(f"Tahun '{y}' tidak valid.")

        return await self._repo.list_budgets_with_progress(owner_jid, m, y)

    async def delete_budget(
        self,
        owner_jid: str,
        category_name: str,
        month: int | None = None,
        year: int | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        m = month if month is not None else now.month
        y = year if year is not None else now.year

        if not (1 <= m <= 12):
            raise FinanceServiceError(f"Bulan '{m}' tidak valid. Harus bernilai 1-12.")
        if y < 2000 or y > 2100:
            raise FinanceServiceError(f"Tahun '{y}' tidak valid.")

        category = await self.resolve_expense_category(owner_jid, category_name)
        success = await self._repo.delete_budget(owner_jid, category.id, m, y)
        if not success:
            raise BudgetNotFoundError(
                f"Budget untuk kategori '{category.name}' pada bulan {m}/{y} tidak ditemukan."
            )
        logger.info("Budget deleted", owner=owner_jid, category=category.name, month=m, year=y)
        return True

    # ── Reset ──────────────────────────────────────────────────────────────────

    async def get_reset_preview(self, owner_jid: str) -> dict[str, int]:
        """Return hitungan data finance yang akan dihapus tanpa menghapusnya."""
        accounts = await self._repo.get_accounts(owner_jid)
        now = datetime.now(UTC)
        transactions = await self._repo.get_transactions(owner_jid, limit=9999)
        budgets = await self._repo.get_budgets(owner_jid, now.month, now.year)
        categories = await self._repo.get_categories(owner_jid)
        return {
            "accounts": len(accounts),
            "transactions": len(transactions),
            "budgets": len(budgets),
            "categories": len(categories),
        }

    async def reset_all_data(self, owner_jid: str) -> dict[str, int]:
        """Hapus semua data finance milik owner_jid. Return jumlah baris yang dihapus."""
        counts = await self._repo.reset_all_data(owner_jid)
        logger.warning(
            "Finance data reset executed",
            owner=owner_jid,
            deleted=counts,
        )
        return counts



