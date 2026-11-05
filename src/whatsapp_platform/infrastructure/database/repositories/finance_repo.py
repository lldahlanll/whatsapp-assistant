"""SQLAlchemyFinanceRepository — concrete implementation of IFinanceRepository."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    BudgetProgress,
    CategorySummary,
    CategoryType,
    FinanceAccount,
    FinanceAuditEntry,
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    MonthlySummary,
    TransactionType,
)
from whatsapp_platform.domain.exceptions import (
    FinanceBalanceConflictError,
    FinanceTransactionConflictError,
)
from whatsapp_platform.domain.repositories.finance_repository import IFinanceRepository
from whatsapp_platform.infrastructure.database.models import (
    FinanceAccountModel,
    FinanceAuditLogModel,
    FinanceBudgetModel,
    FinanceCategoryModel,
    FinanceTransactionModel,
)
from whatsapp_platform.shared.utils.timezone import day_bounds_utc, month_bounds_utc


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
        is_recurring=bool(m.is_recurring),
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


def _row_snapshot(model: Any, **extra: Any) -> dict[str, Any]:
    """Salin semua kolom baris ORM ke dict yang aman untuk JSON (Decimal/datetime -> str)."""
    data = {c.key: getattr(model, c.key) for c in model.__mapper__.column_attrs}
    data.update(extra)
    return json.loads(json.dumps(data, default=str))


def _add_audit(
    session: AsyncSession,
    owner_jid: str,
    entity_type: str,
    entity_id: str | None,
    action: str,
    summary: str,
    snapshot: dict[str, Any],
) -> None:
    """Tambah catatan audit ke session yang sama dengan penghapusan (satu transaksi DB)."""
    session.add(
        FinanceAuditLogModel(
            id=str(uuid.uuid4()),
            owner_jid=owner_jid,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary,
            snapshot=json.dumps(snapshot, ensure_ascii=False),
            created_at=datetime.now(UTC),
        )
    )


class SQLAlchemyFinanceRepository(IFinanceRepository):
    def __init__(
        self,
        session_factory: Any,
        pre_destructive_snapshot: Callable[[str], Path | None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        # Dipanggil sebelum operasi yang tidak bisa dibatalkan (reset); gagal = operasi dibatalkan.
        self._pre_destructive_snapshot = pre_destructive_snapshot

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
        """Ambil rekening AKTIF milik owner; rekening yang sudah dihapus tidak bisa dipakai lagi."""
        async with self._session() as session:
            result = await session.execute(
                select(FinanceAccountModel).where(
                    FinanceAccountModel.id == account_id,
                    FinanceAccountModel.owner_jid == owner_jid,
                    FinanceAccountModel.is_active.is_(True),
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
            _add_audit(
                session, owner_jid, "account", m.id, "delete",
                f"Rekening {m.name} ({m.account_type}), saldo {m.balance}",
                _row_snapshot(m),
            )
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
            try:
                await session.commit()
            except IntegrityError:
                # Seed bersamaan: kategori yang sama sudah dibuat proses lain -> pakai yang ada.
                await session.rollback()
                existing = await self._get_category_exact(
                    session, category.owner_jid, category.category_type.value, category.name
                )
                if existing is None:
                    raise
                return _category_from_model(existing)
            await session.refresh(model)
            return _category_from_model(model)

    @staticmethod
    async def _get_category_exact(
        session: AsyncSession, owner_jid: str, category_type: str, name: str
    ) -> FinanceCategoryModel | None:
        result = await session.execute(
            select(FinanceCategoryModel).where(
                FinanceCategoryModel.owner_jid == owner_jid,
                FinanceCategoryModel.category_type == category_type,
                FinanceCategoryModel.name == name,
            )
        )
        return result.scalars().first()

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
                # Toleran terhadap duplikat lama: ambil yang paling awal, jangan error.
                .order_by(FinanceCategoryModel.created_at, FinanceCategoryModel.id)
                .limit(1)
            )
            m = result.scalars().first()
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
        self, transaction: FinanceTransaction, balance_deltas: dict[str, Decimal]
    ) -> FinanceTransaction:
        try:
            return await self._save_transaction_atomic(transaction, balance_deltas)
        except IntegrityError:
            # Pesan yang sama diproses bersamaan: unique index idempotency_key menolak yang kedua.
            # Transaksi & perubahan saldo kedua sudah di-rollback; kembalikan yang pertama.
            if transaction.idempotency_key:
                existing = await self.get_transaction_by_idempotency_key(
                    transaction.owner_jid, transaction.idempotency_key
                )
                if existing is not None:
                    return existing
            raise

    async def _save_transaction_atomic(
        self, transaction: FinanceTransaction, balance_deltas: dict[str, Decimal]
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
                await session.flush()  # INSERT lebih dulu: bentrok idempotency terdeteksi sebelum saldo berubah
                await self._apply_balance_deltas(session, transaction.owner_jid, balance_deltas)

            await session.refresh(model)
            return _transaction_from_model(
                model,
                account_name=transaction.account_name,
                category_name=transaction.category_name,
                category_icon=transaction.category_icon,
                transfer_to_account_name=transaction.transfer_to_account_name,
            )

    async def reverse_transaction_atomic(
        self, original_tx_id: str, owner_jid: str, reversal_tx: FinanceTransaction, balance_deltas: dict[str, Decimal]
    ) -> FinanceTransaction:
        async with self._session() as session:
            async with session.begin():
                # Conditional update: dua reversal bersamaan hanya satu yang lolos.
                orig_result = await session.execute(
                    update(FinanceTransactionModel)
                    .where(
                        FinanceTransactionModel.id == original_tx_id,
                        FinanceTransactionModel.owner_jid == owner_jid,
                        FinanceTransactionModel.is_reversed.is_(False),
                        FinanceTransactionModel.reversal_of_id.is_(None),
                        # Data yang dipakai menghitung delta harus masih sama (bukan hasil edit bersamaan).
                        FinanceTransactionModel.amount == reversal_tx.amount,
                        FinanceTransactionModel.account_id == reversal_tx.account_id,
                        (
                            FinanceTransactionModel.transfer_to_account_id.is_(None)
                            if reversal_tx.transfer_to_account_id is None
                            else FinanceTransactionModel.transfer_to_account_id
                            == reversal_tx.transfer_to_account_id
                        ),
                    )
                    .values(is_reversed=True)
                )
                if orig_result.rowcount != 1:
                    raise FinanceTransactionConflictError(original_tx_id)

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
                await self._apply_balance_deltas(session, owner_jid, balance_deltas)

            await session.refresh(rev_model)
            return _transaction_from_model(
                rev_model,
                account_name=reversal_tx.account_name,
                category_name=reversal_tx.category_name,
                category_icon=reversal_tx.category_icon,
                transfer_to_account_name=reversal_tx.transfer_to_account_name,
            )

    async def update_transaction_atomic(
        self, transaction: FinanceTransaction, balance_deltas: dict[str, Decimal]
    ) -> FinanceTransaction:
        async with self._session() as session:
            async with session.begin():
                values: dict[str, Any] = {
                    "amount": transaction.amount,
                    "description": transaction.description,
                    "category_id": transaction.category_id,
                    "account_id": transaction.account_id,
                    "transfer_to_account_id": transaction.transfer_to_account_id,
                }
                if transaction.transaction_date:
                    values["transaction_date"] = transaction.transaction_date

                # Conditional update: transaksi yang sudah di-reverse (atau baris reversal) tidak boleh diedit.
                updated = await session.execute(
                    update(FinanceTransactionModel)
                    .where(
                        FinanceTransactionModel.id == transaction.id,
                        FinanceTransactionModel.owner_jid == transaction.owner_jid,
                        FinanceTransactionModel.is_reversed.is_(False),
                        FinanceTransactionModel.reversal_of_id.is_(None),
                    )
                    .values(**values)
                )
                if updated.rowcount != 1:  # type: ignore[attr-defined]
                    exists = await session.execute(
                        select(FinanceTransactionModel.id).where(
                            FinanceTransactionModel.id == transaction.id,
                            FinanceTransactionModel.owner_jid == transaction.owner_jid,
                        )
                    )
                    if exists.scalar_one_or_none() is None:
                        raise ValueError(f"Transaction '{transaction.id}' not found for update.")
                    raise FinanceTransactionConflictError(transaction.id)

                model = (
                    await session.execute(
                        select(FinanceTransactionModel).where(FinanceTransactionModel.id == transaction.id)
                    )
                ).scalar_one()
                await self._apply_balance_deltas(session, transaction.owner_jid, balance_deltas)

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
                    FinanceTransactionModel.deleted_at.is_(None),
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
        date: date_type | datetime | None = None,
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
                # Match same local calendar day
                day = date.date() if isinstance(date, datetime) else date
                day_start, day_end = day_bounds_utc(day)
                q = q.where(
                    FinanceTransactionModel.transaction_date >= day_start,
                    FinanceTransactionModel.transaction_date < day_end,
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
        """Soft delete transaksi (baris tetap ada, ditandai deleted_at) dan kembalikan saldo."""
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    select(FinanceTransactionModel).where(
                        (FinanceTransactionModel.id == tx_id)
                        | (FinanceTransactionModel.human_tx_id == tx_id),
                        FinanceTransactionModel.owner_jid == owner_jid,
                        FinanceTransactionModel.is_reversed.is_(False),
                        FinanceTransactionModel.reversal_of_id.is_(None),
                        FinanceTransactionModel.deleted_at.is_(None),
                    )
                )
                tx_m = result.scalar_one_or_none()
                if not tx_m:
                    return False

                # Conditional update lebih dulu: dua penghapusan bersamaan hanya satu yang mengubah saldo.
                marked = await session.execute(
                    update(FinanceTransactionModel)
                    .where(
                        FinanceTransactionModel.id == tx_m.id,
                        FinanceTransactionModel.is_reversed.is_(False),
                        FinanceTransactionModel.deleted_at.is_(None),
                    )
                    .values(is_reversed=True, deleted_at=datetime.now(UTC))
                )
                if marked.rowcount != 1:  # type: ignore[attr-defined]
                    return False

                acc_names = {
                    a.id: a.name
                    for a in (
                        await session.execute(
                            select(FinanceAccountModel).where(
                                FinanceAccountModel.id.in_(
                                    [i for i in (tx_m.account_id, tx_m.transfer_to_account_id) if i]
                                )
                            )
                        )
                    ).scalars()
                }
                cat_name = None
                if tx_m.category_id:
                    cat = (
                        await session.execute(
                            select(FinanceCategoryModel).where(
                                FinanceCategoryModel.id == tx_m.category_id
                            )
                        )
                    ).scalar_one_or_none()
                    cat_name = cat.name if cat else None
                _add_audit(
                    session, owner_jid, "transaction", tx_m.id, "delete",
                    f"{tx_m.transaction_type} {tx_m.amount} - {tx_m.description or '-'}",
                    _row_snapshot(
                        tx_m,
                        account_name=acc_names.get(tx_m.account_id),
                        transfer_to_account_name=acc_names.get(tx_m.transfer_to_account_id),
                        category_name=cat_name,
                    ),
                )

                # Kembalikan saldo akun
                tx_type = tx_m.transaction_type
                amount = Decimal(str(tx_m.amount))
                deltas: dict[str, Decimal] = {}
                if tx_type == TransactionType.INCOME.value:
                    # Batalkan income: kurangi saldo
                    deltas[tx_m.account_id] = -amount
                elif tx_type == TransactionType.EXPENSE.value:
                    # Batalkan expense: tambah saldo
                    deltas[tx_m.account_id] = amount
                elif tx_type == TransactionType.TRANSFER.value:
                    # Batalkan transfer: kembalikan saldo from, kurangi saldo to
                    deltas[tx_m.account_id] = amount
                    if tx_m.transfer_to_account_id:
                        deltas[tx_m.transfer_to_account_id] = -amount
                # Hapus transaksi memang boleh membuat saldo minus (perilaku lama dipertahankan).
                await self._apply_balance_deltas(session, owner_jid, deltas, allow_negative=True)
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

        start, end = month_bounds_utc(year, month)

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

    async def _apply_balance_deltas(
        self,
        session: AsyncSession,
        owner_jid: str,
        balance_deltas: dict[str, Decimal],
        allow_negative: bool = False,
    ) -> None:
        """Terapkan perubahan saldo relatif (balance = balance + delta) dalam transaksi aktif.

        Update relatif di level SQL mencegah lost update ketika dua pesan memproses
        rekening yang sama bersamaan. Delta negatif ditolak jika membuat saldo minus.
        """
        for acc_id, delta in balance_deltas.items():
            if delta == 0:
                continue
            stmt = (
                update(FinanceAccountModel)
                .where(
                    FinanceAccountModel.id == acc_id,
                    FinanceAccountModel.owner_jid == owner_jid,
                )
                .values(balance=FinanceAccountModel.balance + delta)
            )
            if not allow_negative:
                # Backstop atomik: rekening nonaktif tidak boleh bertransaksi lagi.
                stmt = stmt.where(FinanceAccountModel.is_active.is_(True))
                if delta < 0:
                    # round(): saldo disimpan sebagai REAL di SQLite; hindari penolakan salah akibat error float.
                    stmt = stmt.where(func.round(FinanceAccountModel.balance + delta, 2) >= 0)
            result = await session.execute(stmt)
            if result.rowcount != 1:
                raise FinanceBalanceConflictError(acc_id)

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
                model.is_recurring = budget.is_recurring
                model.updated_at = datetime.now(UTC)
            else:
                model = FinanceBudgetModel(
                    id=budget.id,
                    owner_jid=budget.owner_jid,
                    category_id=budget.category_id,
                    amount=budget.amount,
                    month=budget.month,
                    year=budget.year,
                    is_recurring=budget.is_recurring,
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
            cat = (
                await session.execute(
                    select(FinanceCategoryModel).where(FinanceCategoryModel.id == category_id)
                )
            ).scalar_one_or_none()
            cat_name = cat.name if cat else None
            _add_audit(
                session, owner_jid, "budget", model.id, "delete",
                f"Budget {cat_name or category_id} {month:02d}/{year}: {model.amount}",
                _row_snapshot(model, category_name=cat_name),
            )
            await session.delete(model)
            # Hentikan perulangan: bulan-bulan sebelumnya tidak boleh menyalin ulang budget ini.
            await session.execute(
                update(FinanceBudgetModel)
                .where(
                    FinanceBudgetModel.owner_jid == owner_jid,
                    FinanceBudgetModel.category_id == category_id,
                )
                .values(is_recurring=False)
            )
            await session.commit()
            return True

    async def carry_over_recurring_budgets(
        self, owner_jid: str, month: int, year: int
    ) -> int:
        target = year * 12 + month
        async with self._session() as session:
            existing = set(
                (
                    await session.execute(
                        select(FinanceBudgetModel.category_id).where(
                            FinanceBudgetModel.owner_jid == owner_jid,
                            FinanceBudgetModel.month == month,
                            FinanceBudgetModel.year == year,
                        )
                    )
                ).scalars()
            )
            earlier = (
                await session.execute(
                    select(FinanceBudgetModel)
                    .where(
                        FinanceBudgetModel.owner_jid == owner_jid,
                        (FinanceBudgetModel.year * 12 + FinanceBudgetModel.month) < target,
                    )
                    .order_by(FinanceBudgetModel.year.desc(), FinanceBudgetModel.month.desc())
                )
            ).scalars().all()

            seen: set[str] = set()
            created = 0
            now = datetime.now(UTC)
            for src in earlier:
                if src.category_id in seen:
                    continue
                seen.add(src.category_id)  # hanya baris terbaru per kategori yang menentukan
                if src.category_id in existing or not src.is_recurring:
                    continue
                session.add(
                    FinanceBudgetModel(
                        id=str(uuid.uuid4()),
                        owner_jid=owner_jid,
                        category_id=src.category_id,
                        amount=src.amount,
                        month=month,
                        year=year,
                        is_recurring=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
            if not created:
                return 0
            try:
                await session.commit()
            except IntegrityError:
                # Request lain sudah menyalin lebih dulu; aman diabaikan.
                await session.rollback()
                return 0
            return created

    async def get_budget_progress(
        self, owner_jid: str, category_id: str, month: int, year: int
    ) -> BudgetProgress | None:
        budget = await self.get_budget(owner_jid, category_id, month, year)
        if not budget:
            return None

        start, end = month_bounds_utc(year, month)

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

        start, end = month_bounds_utc(year, month)

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

        if self._pre_destructive_snapshot is not None:
            # Gagal membuat snapshot = reset dibatalkan (data tidak boleh hilang tanpa cadangan).
            await asyncio.to_thread(self._pre_destructive_snapshot, "pre-reset")

        async with self._session() as session:
            # Urutan penting: hapus dependant dulu sebelum parent
            counts: dict[str, int] = {}

            # Audit: simpan semua baris yang akan dihapus (satu catatan per baris, satu transaksi DB).
            for model_cls, etype in (
                (FinanceTransactionModel, "transaction"),
                (FinanceBudgetModel, "budget"),
                (FinanceAccountModel, "account"),
                (FinanceCategoryModel, "category"),
            ):
                rows = (
                    await session.execute(
                        select(model_cls).where(model_cls.owner_jid == owner_jid)
                    )
                ).scalars()
                for row in rows:
                    _add_audit(
                        session, owner_jid, etype, row.id, "reset",
                        f"Reset data: {etype}", _row_snapshot(row),
                    )

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


    # ── Audit log ─────────────────────────────────────────────────────────────

    async def get_audit_log(
        self, owner_jid: str, limit: int = 20, entity_type: str | None = None
    ) -> list[FinanceAuditEntry]:
        async with self._session() as session:
            q = select(FinanceAuditLogModel).where(FinanceAuditLogModel.owner_jid == owner_jid)
            if entity_type:
                q = q.where(FinanceAuditLogModel.entity_type == entity_type)
            q = q.order_by(FinanceAuditLogModel.created_at.desc()).limit(limit)
            rows = (await session.execute(q)).scalars().all()
            return [
                FinanceAuditEntry(
                    id=r.id,
                    owner_jid=r.owner_jid,
                    entity_type=r.entity_type,
                    entity_id=r.entity_id,
                    action=r.action,
                    summary=r.summary,
                    snapshot=json.loads(r.snapshot or "{}"),
                    created_at=r.created_at,
                )
                for r in rows
            ]
