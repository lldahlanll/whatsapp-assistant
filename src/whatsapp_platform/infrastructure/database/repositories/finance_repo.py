"""SQLAlchemyFinanceRepository — concrete implementation of IFinanceRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    BudgetProgress,
    CategorySummary,
    CategoryType,
    FinanceAccount,
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    MonthlySummary,
    TransactionType,
)
from whatsapp_platform.domain.repositories.finance_repository import IFinanceRepository
from whatsapp_platform.infrastructure.database.models import (
    FinanceAccountModel,
    FinanceBudgetModel,
    FinanceCategoryModel,
    FinanceTransactionModel,
)


def _calculate_budget_status(percentage: float) -> str:
    if percentage < 70.0:
        return "aman"
    if percentage < 90.0:
        return "perhatian"
    if percentage <= 100.0:
        return "hampir habis"
    return "melebihi budget"


def _budget_from_model(
    m: FinanceBudgetModel,
    category_name: str | None = None,
    category_icon: str | None = None,
) -> FinanceBudget:
    return FinanceBudget(
        id=m.id,
        owner_jid=m.owner_jid,
        category_id=m.category_id,
        amount=Decimal(str(m.amount)),
        month=m.month,
        year=m.year,
        created_at=m.created_at,
        updated_at=m.updated_at,
        category_name=category_name,
        category_icon=category_icon,
    )



def _account_from_model(m: FinanceAccountModel) -> FinanceAccount:
    return FinanceAccount(
        id=m.id,
        owner_jid=m.owner_jid,
        name=m.name,
        account_type=AccountType(m.account_type),
        currency=m.currency,
        balance=Decimal(str(m.balance)),
        is_active=m.is_active,
        created_at=m.created_at,
    )


def _category_from_model(m: FinanceCategoryModel) -> FinanceCategory:
    return FinanceCategory(
        id=m.id,
        owner_jid=m.owner_jid,
        name=m.name,
        category_type=CategoryType(m.category_type),
        icon=m.icon,
        is_default=m.is_default,
        created_at=m.created_at,
    )


def _transaction_from_model(
    m: FinanceTransactionModel,
    account_name: str | None = None,
    category_name: str | None = None,
    category_icon: str | None = None,
    transfer_to_account_name: str | None = None,
) -> FinanceTransaction:
    return FinanceTransaction(
        id=m.id,
        owner_jid=m.owner_jid,
        account_id=m.account_id,
        transaction_type=TransactionType(m.transaction_type),
        amount=Decimal(str(m.amount)),
        category_id=m.category_id,
        description=m.description,
        transaction_date=m.transaction_date,
        transfer_to_account_id=m.transfer_to_account_id,
        created_at=m.created_at,
        human_tx_id=m.human_tx_id,
        idempotency_key=m.idempotency_key,
        is_reversed=m.is_reversed,
        reversal_of_id=m.reversal_of_id,
        account_name=account_name,
        category_name=category_name,
        category_icon=category_icon,
        transfer_to_account_name=transfer_to_account_name,
    )


class SQLAlchemyFinanceRepository(IFinanceRepository):
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def _session(self) -> AsyncSession:
        return self._session_factory()

    # ── Accounts ──────────────────────────────────────────────────────────────

    async def create_account(self, account: FinanceAccount) -> FinanceAccount:
        async with self._session() as session:
            model = FinanceAccountModel(
                id=account.id,
                owner_jid=account.owner_jid,
                name=account.name,
                account_type=account.account_type.value,
                currency=account.currency,
                balance=account.balance,
                is_active=account.is_active,
                created_at=account.created_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _account_from_model(model)

    async def get_accounts(self, owner_jid: str) -> list[FinanceAccount]:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceAccountModel)
                .where(
                    FinanceAccountModel.owner_jid == owner_jid,
                    FinanceAccountModel.is_active.is_(True),
                )
                .order_by(FinanceAccountModel.created_at)
            )
            return [_account_from_model(m) for m in result.scalars().all()]

    async def get_account_by_id(self, account_id: str, owner_jid: str) -> FinanceAccount | None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceAccountModel).where(
                    FinanceAccountModel.id == account_id,
                    FinanceAccountModel.owner_jid == owner_jid,
                )
            )
            m = result.scalar_one_or_none()
            return _account_from_model(m) if m else None

    async def update_account_balance(self, account_id: str, new_balance: Decimal) -> None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceAccountModel).where(FinanceAccountModel.id == account_id)
            )
            m = result.scalar_one_or_none()
            if m:
                m.balance = new_balance
                await session.commit()

    async def delete_account(self, account_id: str, owner_jid: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceAccountModel).where(
                    FinanceAccountModel.id == account_id,
                    FinanceAccountModel.owner_jid == owner_jid,
                    FinanceAccountModel.is_active.is_(True),
                )
            )
            m = result.scalar_one_or_none()
            if not m:
                return False
            m.is_active = False
            await session.commit()
            return True

    # ── Categories ────────────────────────────────────────────────────────────

    async def create_category(self, category: FinanceCategory) -> FinanceCategory:
        async with self._session() as session:
            model = FinanceCategoryModel(
                id=category.id,
                owner_jid=category.owner_jid,
                name=category.name,
                category_type=category.category_type.value,
                icon=category.icon,
                is_default=category.is_default,
                created_at=category.created_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _category_from_model(model)

    async def get_categories(self, owner_jid: str) -> list[FinanceCategory]:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceCategoryModel)
                .where(FinanceCategoryModel.owner_jid == owner_jid)
                .order_by(FinanceCategoryModel.is_default.desc(), FinanceCategoryModel.name)
            )
            return [_category_from_model(m) for m in result.scalars().all()]

    async def find_category_by_name(
        self, owner_jid: str, name: str
    ) -> FinanceCategory | None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceCategoryModel).where(
                    FinanceCategoryModel.owner_jid == owner_jid,
                    func.lower(FinanceCategoryModel.name) == name.lower(),
                )
            )
            m = result.scalar_one_or_none()
            return _category_from_model(m) if m else None

    # ── Transactions ──────────────────────────────────────────────────────────

    async def add_transaction(self, transaction: FinanceTransaction) -> FinanceTransaction:
        async with self._session() as session:
            model = FinanceTransactionModel(
                id=transaction.id,
                human_tx_id=transaction.human_tx_id,
                idempotency_key=transaction.idempotency_key,
                owner_jid=transaction.owner_jid,
                account_id=transaction.account_id,
                transaction_type=transaction.transaction_type.value,
                amount=transaction.amount,
                category_id=transaction.category_id,
                description=transaction.description,
                transaction_date=transaction.transaction_date,
                transfer_to_account_id=transaction.transfer_to_account_id,
                is_reversed=transaction.is_reversed,
                reversal_of_id=transaction.reversal_of_id,
                created_at=transaction.created_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _transaction_from_model(model)

    async def save_transaction_atomic(
        self, transaction: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction:
        async with self._session() as session:
            async with session.begin():
                model = FinanceTransactionModel(
                    id=transaction.id,
                    human_tx_id=transaction.human_tx_id,
                    idempotency_key=transaction.idempotency_key,
                    owner_jid=transaction.owner_jid,
                    account_id=transaction.account_id,
                    transaction_type=transaction.transaction_type.value,
                    amount=transaction.amount,
                    category_id=transaction.category_id,
                    description=transaction.description,
                    transaction_date=transaction.transaction_date,
                    transfer_to_account_id=transaction.transfer_to_account_id,
                    is_reversed=transaction.is_reversed,
                    reversal_of_id=transaction.reversal_of_id,
                    created_at=transaction.created_at,
                )
                session.add(model)
                for acc_id, new_bal in balance_updates.items():
                    acc_result = await session.execute(
                        select(FinanceAccountModel).where(FinanceAccountModel.id == acc_id)
                    )
                    acc_m = acc_result.scalar_one_or_none()
                    if acc_m:
                        acc_m.balance = new_bal

            await session.refresh(model)
            return _transaction_from_model(
                model,
                account_name=transaction.account_name,
                category_name=transaction.category_name,
                category_icon=transaction.category_icon,
                transfer_to_account_name=transaction.transfer_to_account_name,
            )

    async def reverse_transaction_atomic(
        self, original_tx_id: str, owner_jid: str, reversal_tx: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction:
        async with self._session() as session:
            async with session.begin():
                orig_result = await session.execute(
                    select(FinanceTransactionModel).where(
                        FinanceTransactionModel.id == original_tx_id,
                        FinanceTransactionModel.owner_jid == owner_jid,
                    )
                )
                orig_m = orig_result.scalar_one_or_none()
                if orig_m:
                    orig_m.is_reversed = True

                rev_model = FinanceTransactionModel(
                    id=reversal_tx.id,
                    human_tx_id=reversal_tx.human_tx_id,
                    idempotency_key=reversal_tx.idempotency_key,
                    owner_jid=reversal_tx.owner_jid,
                    account_id=reversal_tx.account_id,
                    transaction_type=reversal_tx.transaction_type.value,
                    amount=reversal_tx.amount,
                    category_id=reversal_tx.category_id,
                    description=reversal_tx.description,
                    transaction_date=reversal_tx.transaction_date,
                    transfer_to_account_id=reversal_tx.transfer_to_account_id,
                    is_reversed=False,
                    reversal_of_id=original_tx_id,
                    created_at=reversal_tx.created_at,
                )
                session.add(rev_model)
                for acc_id, new_bal in balance_updates.items():
                    acc_result = await session.execute(
                        select(FinanceAccountModel).where(FinanceAccountModel.id == acc_id)
                    )
                    acc_m = acc_result.scalar_one_or_none()
                    if acc_m:
                        acc_m.balance = new_bal

            await session.refresh(rev_model)
            return _transaction_from_model(
                rev_model,
                account_name=reversal_tx.account_name,
                category_name=reversal_tx.category_name,
                category_icon=reversal_tx.category_icon,
                transfer_to_account_name=reversal_tx.transfer_to_account_name,
            )

    async def update_transaction_atomic(
        self, transaction: FinanceTransaction, balance_updates: dict[str, Decimal]
    ) -> FinanceTransaction:
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    select(FinanceTransactionModel).where(
                        (FinanceTransactionModel.id == transaction.id)
                        | (FinanceTransactionModel.human_tx_id == transaction.human_tx_id),
                        FinanceTransactionModel.owner_jid == transaction.owner_jid,
                    )
                )
                model = result.scalar_one_or_none()
                if not model:
                    raise ValueError(f"Transaction '{transaction.id}' not found for update.")

                model.amount = transaction.amount
                model.description = transaction.description
                model.category_id = transaction.category_id
                model.account_id = transaction.account_id
                model.transfer_to_account_id = transaction.transfer_to_account_id
                if transaction.transaction_date:
                    model.transaction_date = transaction.transaction_date

                for acc_id, new_bal in balance_updates.items():
                    acc_result = await session.execute(
                        select(FinanceAccountModel).where(FinanceAccountModel.id == acc_id)
                    )
                    acc_m = acc_result.scalar_one_or_none()
                    if acc_m:
                        acc_m.balance = new_bal

            await session.refresh(model)
            return _transaction_from_model(
                model,
                account_name=transaction.account_name,
                category_name=transaction.category_name,
                category_icon=transaction.category_icon,
                transfer_to_account_name=transaction.transfer_to_account_name,
            )

    async def get_transaction_by_id(self, tx_id: str, owner_jid: str) -> FinanceTransaction | None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceTransactionModel).where(
                    (FinanceTransactionModel.id == tx_id) | (FinanceTransactionModel.human_tx_id == tx_id),
                    FinanceTransactionModel.owner_jid == owner_jid,
                )
            )
            m = result.scalar_one_or_none()
            if not m:
                return None

            account_ids = {m.account_id}
            if m.transfer_to_account_id:
                account_ids.add(m.transfer_to_account_id)
            accounts = await self._fetch_accounts_by_ids(session, account_ids)
            categories = await self._fetch_categories_by_ids(
                session, {m.category_id} if m.category_id else set()
            )

            return _transaction_from_model(
                m,
                account_name=accounts.get(m.account_id),
                category_name=categories.get(m.category_id, {}).get("name") if m.category_id else None,
                category_icon=categories.get(m.category_id, {}).get("icon") if m.category_id else None,
                transfer_to_account_name=(
                    accounts.get(m.transfer_to_account_id) if m.transfer_to_account_id else None
                ),
            )

    async def get_transaction_by_idempotency_key(
        self, owner_jid: str, idempotency_key: str
    ) -> FinanceTransaction | None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceTransactionModel).where(
                    FinanceTransactionModel.owner_jid == owner_jid,
                    FinanceTransactionModel.idempotency_key == idempotency_key,
                )
            )
            m = result.scalar_one_or_none()
            if not m:
                return None

            account_ids = {m.account_id}
            if m.transfer_to_account_id:
                account_ids.add(m.transfer_to_account_id)
            accounts = await self._fetch_accounts_by_ids(session, account_ids)
            categories = await self._fetch_categories_by_ids(
                session, {m.category_id} if m.category_id else set()
            )

            return _transaction_from_model(
                m,
                account_name=accounts.get(m.account_id),
                category_name=categories.get(m.category_id, {}).get("name") if m.category_id else None,
                category_icon=categories.get(m.category_id, {}).get("icon") if m.category_id else None,
                transfer_to_account_name=(
                    accounts.get(m.transfer_to_account_id) if m.transfer_to_account_id else None
                ),
            )

    async def get_transactions(
        self,
        owner_jid: str,
        limit: int = 10,
        account_id: str | None = None,
        category_id: str | None = None,
        transaction_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[FinanceTransaction]:
        async with self._session() as session:
            q = select(FinanceTransactionModel).where(
                FinanceTransactionModel.owner_jid == owner_jid,
                FinanceTransactionModel.is_reversed.is_(False),
                FinanceTransactionModel.reversal_of_id.is_(None),
            )
            if account_id:
                q = q.where(FinanceTransactionModel.account_id == account_id)
            if category_id:
                q = q.where(FinanceTransactionModel.category_id == category_id)
            if transaction_type:
                q = q.where(FinanceTransactionModel.transaction_type == transaction_type)
            if date_from:
                q = q.where(FinanceTransactionModel.transaction_date >= date_from)
            if date_to:
                q = q.where(FinanceTransactionModel.transaction_date <= date_to)
            q = q.order_by(FinanceTransactionModel.transaction_date.desc()).limit(limit)

            result = await session.execute(q)
            transactions = result.scalars().all()

            account_ids = {t.account_id for t in transactions}
            cat_ids = {t.category_id for t in transactions if t.category_id}
            transfer_ids = {t.transfer_to_account_id for t in transactions if t.transfer_to_account_id}

            accounts = await self._fetch_accounts_by_ids(session, account_ids | transfer_ids)
            categories = await self._fetch_categories_by_ids(session, cat_ids)

            return [
                _transaction_from_model(
                    t,
                    account_name=accounts.get(t.account_id),
                    category_name=categories.get(t.category_id, {}).get("name"),
                    category_icon=categories.get(t.category_id, {}).get("icon"),
                    transfer_to_account_name=(
                        accounts.get(t.transfer_to_account_id) if t.transfer_to_account_id else None
                    ),
                )
                for t in transactions
            ]

    async def search_transactions(
        self,
        owner_jid: str,
        keyword: str | None = None,
        date: datetime | None = None,
        transaction_type: str | None = None,
        limit: int = 5,
    ) -> list[FinanceTransaction]:
        """Cari transaksi berdasarkan keyword deskripsi dan/atau tanggal."""
        from sqlalchemy import or_

        async with self._session() as session:
            q = select(FinanceTransactionModel).where(
                FinanceTransactionModel.owner_jid == owner_jid,
                FinanceTransactionModel.is_reversed.is_(False),
                FinanceTransactionModel.reversal_of_id.is_(None),
            )
            if keyword:
                pattern = f"%{keyword}%"
                q = q.where(
                    or_(
                        FinanceTransactionModel.description.ilike(pattern),
                        FinanceTransactionModel.human_tx_id.ilike(pattern),
                    )
                )
            if date:
                # Match same calendar day
                day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                q = q.where(
                    FinanceTransactionModel.transaction_date >= day_start,
                    FinanceTransactionModel.transaction_date <= day_end,
                )
            if transaction_type:
                q = q.where(FinanceTransactionModel.transaction_type == transaction_type)

            q = q.order_by(FinanceTransactionModel.transaction_date.desc()).limit(limit)
            result = await session.execute(q)
            transactions = result.scalars().all()

            account_ids = {t.account_id for t in transactions}
            cat_ids = {t.category_id for t in transactions if t.category_id}
            transfer_ids = {t.transfer_to_account_id for t in transactions if t.transfer_to_account_id}
            accounts = await self._fetch_accounts_by_ids(session, account_ids | transfer_ids)
            categories = await self._fetch_categories_by_ids(session, cat_ids)

            return [
                _transaction_from_model(
                    t,
                    account_name=accounts.get(t.account_id),
                    category_name=categories.get(t.category_id, {}).get("name"),
                    category_icon=categories.get(t.category_id, {}).get("icon"),
                    transfer_to_account_name=(
                        accounts.get(t.transfer_to_account_id) if t.transfer_to_account_id else None
                    ),
                )
                for t in transactions
            ]

    async def delete_transaction(
        self,
        tx_id: str,
        owner_jid: str,
    ) -> bool:
        """Hard delete transaksi dan kembalikan saldo ke kondisi sebelumnya."""
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    select(FinanceTransactionModel).where(
                        (FinanceTransactionModel.id == tx_id)
                        | (FinanceTransactionModel.human_tx_id == tx_id),
                        FinanceTransactionModel.owner_jid == owner_jid,
                        FinanceTransactionModel.is_reversed.is_(False),
                    )
                )
                tx_m = result.scalar_one_or_none()
                if not tx_m:
                    return False

                # Kembalikan saldo akun
                acc_result = await session.execute(
                    select(FinanceAccountModel).where(
                        FinanceAccountModel.id == tx_m.account_id
                    )
                )
                acc = acc_result.scalar_one_or_none()
                if acc:
                    tx_type = tx_m.transaction_type
                    amount = Decimal(str(tx_m.amount))
                    if tx_type == TransactionType.INCOME.value:
                        # Batalkan income: kurangi saldo
                        acc.balance = acc.balance - amount
                    elif tx_type == TransactionType.EXPENSE.value:
                        # Batalkan expense: tambah saldo
                        acc.balance = acc.balance + amount
                    elif tx_type == TransactionType.TRANSFER.value:
                        # Batalkan transfer: kembalikan saldo from, kurangi saldo to
                        acc.balance = acc.balance + amount
                        if tx_m.transfer_to_account_id:
                            to_result = await session.execute(
                                select(FinanceAccountModel).where(
                                    FinanceAccountModel.id == tx_m.transfer_to_account_id
                                )
                            )
                            to_acc = to_result.scalar_one_or_none()
                            if to_acc:
                                to_acc.balance = to_acc.balance - amount

                await session.delete(tx_m)
        return True

    async def get_transactions_by_period(
        self,
        owner_jid: str,
        start: datetime,
        end: datetime,
        account_id: str | None = None,
    ) -> list[FinanceTransaction]:
        async with self._session() as session:
            q = select(FinanceTransactionModel).where(
                FinanceTransactionModel.owner_jid == owner_jid,
                FinanceTransactionModel.transaction_date >= start,
                FinanceTransactionModel.transaction_date <= end,
                FinanceTransactionModel.is_reversed.is_(False),
                FinanceTransactionModel.reversal_of_id.is_(None),
            )
            if account_id:
                q = q.where(FinanceTransactionModel.account_id == account_id)
            q = q.order_by(FinanceTransactionModel.transaction_date.desc())
            result = await session.execute(q)
            transactions = result.scalars().all()

            account_ids = {t.account_id for t in transactions}
            cat_ids = {t.category_id for t in transactions if t.category_id}
            transfer_ids = {t.transfer_to_account_id for t in transactions if t.transfer_to_account_id}

            accounts = await self._fetch_accounts_by_ids(session, account_ids | transfer_ids)
            categories = await self._fetch_categories_by_ids(session, cat_ids)

            return [
                _transaction_from_model(
                    t,
                    account_name=accounts.get(t.account_id),
                    category_name=categories.get(t.category_id, {}).get("name"),
                    category_icon=categories.get(t.category_id, {}).get("icon"),
                    transfer_to_account_name=(
                        accounts.get(t.transfer_to_account_id) if t.transfer_to_account_id else None
                    ),
                )
                for t in transactions
            ]

    async def get_monthly_summary(
        self, owner_jid: str, year: int, month: int
    ) -> MonthlySummary:

        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)

        async with self._session() as session:
            result = await session.execute(
                select(
                    FinanceTransactionModel.transaction_type,
                    func.sum(FinanceTransactionModel.amount).label("total"),
                ).where(
                    FinanceTransactionModel.owner_jid == owner_jid,
                    FinanceTransactionModel.transaction_date >= start,
                    FinanceTransactionModel.transaction_date < end,
                    FinanceTransactionModel.is_reversed.is_(False),
                    FinanceTransactionModel.reversal_of_id.is_(None),
                ).group_by(FinanceTransactionModel.transaction_type)
            )
            rows = result.all()

        total_income = Decimal("0")
        total_expense = Decimal("0")
        for row in rows:
            if row.transaction_type == TransactionType.INCOME.value:
                total_income = Decimal(str(row.total or 0))
            elif row.transaction_type == TransactionType.EXPENSE.value:
                total_expense = Decimal(str(row.total or 0))

        cat_summary = await self.get_category_summary(owner_jid, start, end)

        return MonthlySummary(
            year=year,
            month=month,
            total_income=total_income,
            total_expense=total_expense,
            net=total_income - total_expense,
            top_expense_categories=cat_summary[:5],
        )

    async def get_category_summary(
        self, owner_jid: str, start: datetime, end: datetime
    ) -> list[CategorySummary]:
        async with self._session() as session:
            result = await session.execute(
                select(
                    FinanceTransactionModel.category_id,
                    func.sum(FinanceTransactionModel.amount).label("total"),
                    func.count(FinanceTransactionModel.id).label("count"),
                ).where(
                    FinanceTransactionModel.owner_jid == owner_jid,
                    FinanceTransactionModel.transaction_type == TransactionType.EXPENSE.value,
                    FinanceTransactionModel.transaction_date >= start,
                    FinanceTransactionModel.transaction_date < end,
                    FinanceTransactionModel.is_reversed.is_(False),
                    FinanceTransactionModel.reversal_of_id.is_(None),
                ).group_by(FinanceTransactionModel.category_id)
                .order_by(func.sum(FinanceTransactionModel.amount).desc())
            )
            rows = result.all()

        cat_ids = {r.category_id for r in rows if r.category_id}
        categories: dict[str, dict[str, str | None]] = {}
        if cat_ids:
            async with self._session() as session:
                result2 = await session.execute(
                    select(FinanceCategoryModel).where(FinanceCategoryModel.id.in_(cat_ids))
                )
                for c in result2.scalars().all():
                    categories[c.id] = {"name": c.name, "icon": c.icon}

        summaries = []
        for row in rows:
            cat = categories.get(row.category_id or "", {})
            summaries.append(
                CategorySummary(
                    category_name=cat.get("name") or "Lainnya",
                    category_icon=cat.get("icon"),
                    total=Decimal(str(row.total or 0)),
                    transaction_count=row.count,
                )
            )
        return summaries

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _fetch_accounts_by_ids(
        self, session: AsyncSession, ids: set[str]
    ) -> dict[str, str]:
        if not ids:
            return {}
        result = await session.execute(
            select(FinanceAccountModel.id, FinanceAccountModel.name).where(
                FinanceAccountModel.id.in_(ids)
            )
        )
        return {row.id: row.name for row in result.all()}

    async def _fetch_categories_by_ids(
        self, session: AsyncSession, ids: set[str]
    ) -> dict[str, dict[str, str | None]]:
        if not ids:
            return {}
        result = await session.execute(
            select(
                FinanceCategoryModel.id,
                FinanceCategoryModel.name,
                FinanceCategoryModel.icon,
            ).where(FinanceCategoryModel.id.in_(ids))
        )
        return {row.id: {"name": row.name, "icon": row.icon} for row in result.all()}

    # ── Budgets ───────────────────────────────────────────────────────────────

    async def upsert_budget(self, budget: FinanceBudget) -> FinanceBudget:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceBudgetModel).where(
                    FinanceBudgetModel.owner_jid == budget.owner_jid,
                    FinanceBudgetModel.category_id == budget.category_id,
                    FinanceBudgetModel.month == budget.month,
                    FinanceBudgetModel.year == budget.year,
                )
            )
            model = result.scalar_one_or_none()
            if model:
                model.amount = budget.amount
                model.updated_at = datetime.now(UTC)
            else:
                model = FinanceBudgetModel(
                    id=budget.id,
                    owner_jid=budget.owner_jid,
                    category_id=budget.category_id,
                    amount=budget.amount,
                    month=budget.month,
                    year=budget.year,
                    created_at=budget.created_at,
                    updated_at=budget.updated_at,
                )
                session.add(model)
            await session.commit()
            await session.refresh(model)

            categories = await self._fetch_categories_by_ids(session, {model.category_id})
            cat_info = categories.get(model.category_id, {})
            return _budget_from_model(
                model,
                category_name=cat_info.get("name"),
                category_icon=cat_info.get("icon"),
            )

    async def get_budget(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> FinanceBudget | None:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceBudgetModel).where(
                    FinanceBudgetModel.owner_jid == owner_jid,
                    FinanceBudgetModel.category_id == category_id,
                    FinanceBudgetModel.month == month,
                    FinanceBudgetModel.year == year,
                )
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            categories = await self._fetch_categories_by_ids(session, {model.category_id})
            cat_info = categories.get(model.category_id, {})
            return _budget_from_model(
                model,
                category_name=cat_info.get("name"),
                category_icon=cat_info.get("icon"),
            )

    async def get_budgets(
        self, owner_jid: str, month: int, year: int
    ) -> list[FinanceBudget]:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceBudgetModel).where(
                    FinanceBudgetModel.owner_jid == owner_jid,
                    FinanceBudgetModel.month == month,
                    FinanceBudgetModel.year == year,
                ).order_by(FinanceBudgetModel.created_at)
            )
            models = result.scalars().all()
            cat_ids = {m.category_id for m in models}
            categories = await self._fetch_categories_by_ids(session, cat_ids)
            return [
                _budget_from_model(
                    m,
                    category_name=categories.get(m.category_id, {}).get("name"),
                    category_icon=categories.get(m.category_id, {}).get("icon"),
                )
                for m in models
            ]

    async def delete_budget(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(FinanceBudgetModel).where(
                    FinanceBudgetModel.owner_jid == owner_jid,
                    FinanceBudgetModel.category_id == category_id,
                    FinanceBudgetModel.month == month,
                    FinanceBudgetModel.year == year,
                )
            )
            model = result.scalar_one_or_none()
            if not model:
                return False
            await session.delete(model)
            await session.commit()
            return True

    async def get_budget_progress(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> BudgetProgress | None:
        budget = await self.get_budget(owner_jid, category_id, month, year)
        if not budget:
            return None

        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)

        async with self._session() as session:
            result = await session.execute(
                select(func.sum(FinanceTransactionModel.amount)).where(
                    FinanceTransactionModel.owner_jid == owner_jid,
                    FinanceTransactionModel.category_id == category_id,
                    FinanceTransactionModel.transaction_type == TransactionType.EXPENSE.value,
                    FinanceTransactionModel.transaction_date >= start,
                    FinanceTransactionModel.transaction_date < end,
                    FinanceTransactionModel.is_reversed.is_(False),
                    FinanceTransactionModel.reversal_of_id.is_(None),
                )
            )
            total_spent_val = result.scalar() or 0
            spent = Decimal(str(total_spent_val))

        remaining = budget.amount - spent
        percentage = float((spent / budget.amount) * 100) if budget.amount > 0 else 0.0
        status = _calculate_budget_status(percentage)

        return BudgetProgress(
            budget=budget,
            spent=spent,
            remaining=remaining,
            percentage=percentage,
            status=status,
        )

    async def list_budgets_with_progress(
        self, owner_jid: str, month: int, year: int
    ) -> list[BudgetProgress]:
        budgets = await self.get_budgets(owner_jid, month, year)
        if not budgets:
            return []

        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)

        cat_ids = [b.category_id for b in budgets]
        async with self._session() as session:
            result = await session.execute(
                select(
                    FinanceTransactionModel.category_id,
                    func.sum(FinanceTransactionModel.amount).label("total_spent"),
                ).where(
                    FinanceTransactionModel.owner_jid == owner_jid,
                    FinanceTransactionModel.category_id.in_(cat_ids),
                    FinanceTransactionModel.transaction_type == TransactionType.EXPENSE.value,
                    FinanceTransactionModel.transaction_date >= start,
                    FinanceTransactionModel.transaction_date < end,
                    FinanceTransactionModel.is_reversed.is_(False),
                    FinanceTransactionModel.reversal_of_id.is_(None),
                ).group_by(FinanceTransactionModel.category_id)
            )
            spent_map = {
                row.category_id: Decimal(str(row.total_spent or 0))
                for row in result.all()
            }

        progress_list = []
        for b in budgets:
            spent = spent_map.get(b.category_id, Decimal("0"))
            remaining = b.amount - spent
            percentage = float((spent / b.amount) * 100) if b.amount > 0 else 0.0
            status = _calculate_budget_status(percentage)
            progress_list.append(
                BudgetProgress(
                    budget=b,
                    spent=spent,
                    remaining=remaining,
                    percentage=percentage,
                    status=status,
                )
            )
        return progress_list

    # ── Reset ──────────────────────────────────────────────────────────────────

    async def reset_all_data(self, owner_jid: str) -> dict[str, int]:
        """Hapus semua data finance milik owner_jid dan return jumlah baris per tabel."""
        from sqlalchemy import delete as sa_delete

        async with self._session() as session:
            # Urutan penting: hapus dependant dulu sebelum parent
            counts: dict[str, int] = {}

            res = await session.execute(
                sa_delete(FinanceTransactionModel).where(
                    FinanceTransactionModel.owner_jid == owner_jid
                )
            )
            counts["transactions"] = res.rowcount

            res = await session.execute(
                sa_delete(FinanceBudgetModel).where(
                    FinanceBudgetModel.owner_jid == owner_jid
                )
            )
            counts["budgets"] = res.rowcount

            res = await session.execute(
                sa_delete(FinanceAccountModel).where(
                    FinanceAccountModel.owner_jid == owner_jid
                )
            )
            counts["accounts"] = res.rowcount

            res = await session.execute(
                sa_delete(FinanceCategoryModel).where(
                    FinanceCategoryModel.owner_jid == owner_jid
                )
            )
            counts["categories"] = res.rowcount

            await session.commit()
            return counts

