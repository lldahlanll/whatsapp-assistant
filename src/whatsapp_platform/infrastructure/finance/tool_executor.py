"""FinanceToolExecutor — dispatches LLM finance tool calls to FinanceService."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.features.finance.service import (
    AccountNotFoundError,
    AccountRequiredError,
    BudgetNotFoundError,
    CategoryNotFoundError,
    InsufficientBalanceError,
    InvalidAmountError,
    TransactionNotFoundError,
)

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID
    from whatsapp_platform.features.finance.service import FinanceService

logger = structlog.get_logger()


class FinanceToolExecutor:
    def __init__(self, finance_service: FinanceService) -> None:
        self._svc = finance_service

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
    ) -> str:
        owner_jid = str(user_jid)
        logger.info(
            "Executing finance tool call",
            tool=tool_name,
            arguments=arguments,
            owner=owner_jid,
        )

        try:
            if tool_name == "finance_add_income":
                return await self._add_income(owner_jid, arguments)

            elif tool_name == "finance_add_expense":
                return await self._add_expense(owner_jid, arguments)

            elif tool_name == "finance_transfer":
                return await self._transfer(owner_jid, arguments)

            elif tool_name == "finance_get_balance":
                return await self._get_balance(owner_jid)

            elif tool_name == "finance_get_monthly_report":
                return await self._get_monthly_report(owner_jid, arguments)

            elif tool_name == "finance_get_transactions":
                return await self._get_transactions(owner_jid, arguments)

            elif tool_name == "finance_get_expense_summary":
                return await self._get_expense_summary(owner_jid, arguments)

            elif tool_name == "finance_create_account":
                return await self._create_account(owner_jid, arguments)

            elif tool_name == "finance_get_accounts":
                return await self._get_accounts(owner_jid)

            elif tool_name == "finance_get_categories":
                return await self._get_categories(owner_jid, arguments)

            elif tool_name == "finance_get_transaction_detail":
                return await self._get_transaction_detail(owner_jid, arguments)

            elif tool_name == "finance_update_transaction":
                return await self._update_transaction(owner_jid, arguments)

            elif tool_name == "finance_delete_transaction":
                return await self._delete_transaction(owner_jid, arguments)

            elif tool_name == "finance_create_budget":
                return await self._create_budget(owner_jid, arguments)

            elif tool_name == "finance_get_budget":
                return await self._get_budget(owner_jid, arguments)

            elif tool_name == "finance_list_budgets":
                return await self._list_budgets(owner_jid, arguments)

            elif tool_name == "finance_delete_budget":
                return await self._delete_budget(owner_jid, arguments)

            else:
                return json.dumps({
                    "status": "error",
                    "error_code": "INVALID_TOOL",
                    "message": f"Tool '{tool_name}' tidak dikenali.",
                }, ensure_ascii=False)

        except AccountNotFoundError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "ACCOUNT_NOT_FOUND",
                "message": str(exc),
            }, ensure_ascii=False)
        except AccountRequiredError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "ACCOUNT_REQUIRED",
                "message": str(exc),
            }, ensure_ascii=False)
        except InsufficientBalanceError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "INSUFFICIENT_BALANCE",
                "message": str(exc),
            }, ensure_ascii=False)
        except InvalidAmountError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "INVALID_AMOUNT",
                "message": str(exc),
            }, ensure_ascii=False)
        except TransactionNotFoundError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "TRANSACTION_NOT_FOUND",
                "message": str(exc),
            }, ensure_ascii=False)
        except CategoryNotFoundError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "CATEGORY_NOT_FOUND",
                "message": str(exc),
            }, ensure_ascii=False)
        except BudgetNotFoundError as exc:
            return json.dumps({
                "status": "error",
                "error_code": "BUDGET_NOT_FOUND",
                "message": str(exc),
            }, ensure_ascii=False)
        except Exception as exc:
            logger.error("Finance tool execution error", tool=tool_name, error=str(exc))
            return json.dumps({
                "status": "error",
                "error_code": "FINANCE_ERROR",
                "message": str(exc),
            }, ensure_ascii=False)

    # ── Handlers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_tx_date(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None

    async def _add_income(self, owner_jid: str, args: dict) -> str:
        amount = Decimal(str(args["amount"]))
        account_name: str | None = args.get("account_name")
        account_id = None
        if account_name:
            acc = await self._svc.find_account_by_name(owner_jid, account_name)
            if not acc:
                raise AccountNotFoundError(
                    f"Account '{account_name}' belum terdaftar. Mau saya tambahkan sebagai rekening baru?"
                )
            account_id = acc.id

        date = self._parse_tx_date(args.get("date"))
        tx = await self._svc.add_income(
            owner_jid=owner_jid,
            amount=amount,
            description=args.get("description"),
            category_name=args.get("category_name"),
            account_id=account_id,
            date=date,
            idempotency_key=args.get("idempotency_key"),
        )
        current_acc = await self._svc._repo.get_account_by_id(tx.account_id, owner_jid)
        date_str = (
            tx.transaction_date.strftime("%Y-%m-%d")
            if tx.transaction_date
            else datetime.now(UTC).strftime("%Y-%m-%d")
        )
        return json.dumps({
            "status": "success",
            "transaction_id": tx.human_tx_id or tx.id,
            "date": date_str,
            "type": "income",
            "amount": float(amount),
            "account_name": tx.account_name,
            "category": tx.category_name,
            "description": tx.description,
            "new_balance": float(current_acc.balance) if current_acc else None,
            "message": (
                f"Pemasukan Rp {int(amount):,} berhasil dicatat ke {tx.account_name}."
            ),
        }, ensure_ascii=False)

    async def _add_expense(self, owner_jid: str, args: dict) -> str:
        amount = Decimal(str(args["amount"]))
        account_name: str | None = args.get("account_name")
        account_id = None
        if account_name:
            acc = await self._svc.find_account_by_name(owner_jid, account_name)
            if not acc:
                raise AccountNotFoundError(
                    f"Account '{account_name}' belum terdaftar. Mau saya tambahkan sebagai rekening baru?"
                )
            account_id = acc.id

        date = self._parse_tx_date(args.get("date"))
        tx = await self._svc.add_expense(
            owner_jid=owner_jid,
            amount=amount,
            description=args.get("description"),
            category_name=args.get("category_name"),
            account_id=account_id,
            date=date,
            idempotency_key=args.get("idempotency_key"),
        )
        current_acc = await self._svc._repo.get_account_by_id(tx.account_id, owner_jid)
        date_str = (
            tx.transaction_date.strftime("%Y-%m-%d")
            if tx.transaction_date
            else datetime.now(UTC).strftime("%Y-%m-%d")
        )
        return json.dumps({
            "status": "success",
            "transaction_id": tx.human_tx_id or tx.id,
            "date": date_str,
            "type": "expense",
            "amount": float(amount),
            "account_name": tx.account_name,
            "category": tx.category_name,
            "description": tx.description,
            "new_balance": float(current_acc.balance) if current_acc else None,
            "message": (
                f"Pengeluaran Rp {int(amount):,} dari {tx.account_name} berhasil dicatat."
            ),
        }, ensure_ascii=False)

    async def _transfer(self, owner_jid: str, args: dict) -> str:
        amount = Decimal(str(args["amount"]))
        from_acc = await self._svc.find_account_by_name(owner_jid, args["from_account_name"])
        to_acc = await self._svc.find_account_by_name(owner_jid, args["to_account_name"])

        if not from_acc:
            raise AccountNotFoundError(f"Rekening asal '{args['from_account_name']}' tidak ditemukan.")
        if not to_acc:
            raise AccountNotFoundError(f"Rekening tujuan '{args['to_account_name']}' tidak ditemukan.")

        date = self._parse_tx_date(args.get("date"))
        tx = await self._svc.transfer(
            owner_jid=owner_jid,
            amount=amount,
            from_account_id=from_acc.id,
            to_account_id=to_acc.id,
            description=args.get("description"),
            date=date,
            idempotency_key=args.get("idempotency_key"),
        )
        updated_from = await self._svc._repo.get_account_by_id(from_acc.id, owner_jid)
        updated_to = await self._svc._repo.get_account_by_id(to_acc.id, owner_jid)
        date_str = (
            tx.transaction_date.strftime("%Y-%m-%d")
            if tx.transaction_date
            else datetime.now(UTC).strftime("%Y-%m-%d")
        )
        return json.dumps({
            "status": "success",
            "transaction_id": tx.human_tx_id or tx.id,
            "date": date_str,
            "type": "transfer",
            "amount": float(amount),
            "from_account": from_acc.name,
            "to_account": to_acc.name,
            "from_new_balance": float(updated_from.balance) if updated_from else None,
            "to_new_balance": float(updated_to.balance) if updated_to else None,
            "message": (
                f"Transfer Rp {int(amount):,} dari {from_acc.name} ke {to_acc.name} berhasil."
            ),
        }, ensure_ascii=False)

    async def _get_balance(self, owner_jid: str) -> str:
        data = await self._svc.get_total_balance(owner_jid)
        return json.dumps({
            "status": "success",
            "total_balance": float(data["total"]),
            "currency": "IDR",
            "accounts": [
                {
                    "name": a["name"],
                    "balance": float(a["balance"]),
                    "type": a["type"],
                }
                for a in data["accounts"]
            ],
        }, ensure_ascii=False)

    async def _get_monthly_report(self, owner_jid: str, args: dict) -> str:
        summary = await self._svc.get_monthly_report(
            owner_jid,
            year=args.get("year"),
            month=args.get("month"),
        )
        return json.dumps({
            "status": "success",
            "year": summary.year,
            "month": summary.month,
            "total_income": float(summary.total_income),
            "total_expense": float(summary.total_expense),
            "net": float(summary.net),
            "top_expense_categories": [
                {
                    "name": c.category_name,
                    "icon": c.category_icon,
                    "total": float(c.total),
                    "count": c.transaction_count,
                }
                for c in summary.top_expense_categories
            ],
        }, ensure_ascii=False)

    async def _get_transactions(self, owner_jid: str, args: dict) -> str:
        from datetime import datetime

        limit_val = args.get("limit")
        try:
            limit = min(int(limit_val), 30) if limit_val is not None else 10
        except (ValueError, TypeError):
            limit = 10

        account_id = None
        account_name: str | None = args.get("account_name")
        if account_name:
            acc = await self._svc.find_account_by_name(owner_jid, account_name)
            if acc:
                account_id = acc.id

        # Filter kategori → resolve ke category_id
        category_id = None
        category_name: str | None = args.get("category_name")
        if category_name:
            cats = await self._svc.get_categories(owner_jid)
            for c in cats:
                if c.name.lower() == category_name.lower() or category_name.lower() in c.name.lower():
                    category_id = c.id
                    break

        # Parse date_from / date_to
        def _parse_date(val: str | None):
            if not val:
                return None
            try:
                return datetime.fromisoformat(val).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                return None

        date_from = _parse_date(args.get("date_from"))
        date_to = _parse_date(args.get("date_to"))
        transaction_type: str | None = args.get("transaction_type")

        transactions = await self._svc.get_recent_transactions(
            owner_jid,
            limit=limit,
            account_id=account_id,
            transaction_type=transaction_type,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
        )
        return json.dumps({
            "status": "success",
            "count": len(transactions),
            "transactions": [
                {
                    "transaction_id": tx.human_tx_id or tx.id,
                    "date": tx.transaction_date.strftime("%Y-%m-%d"),
                    "type": tx.transaction_type.value,
                    "amount": float(tx.amount),
                    "description": tx.description,
                    "category": tx.category_name,
                    "account": tx.account_name,
                }
                for tx in transactions
            ],
        }, ensure_ascii=False)

    async def _get_expense_summary(self, owner_jid: str, args: dict) -> str:
        summary = await self._svc.get_expense_summary(
            owner_jid,
            year=args.get("year"),
            month=args.get("month"),
        )
        return json.dumps({
            "status": "success",
            "expense_by_category": [
                {
                    "name": c.category_name,
                    "icon": c.category_icon,
                    "total": float(c.total),
                    "count": c.transaction_count,
                }
                for c in summary
            ],
        }, ensure_ascii=False)

    async def _create_account(self, owner_jid: str, args: dict) -> str:
        from whatsapp_platform.domain.entities.finance import AccountType

        name = args["name"]
        raw_type = (args.get("account_type") or "bank").lower()
        type_map = {
            "cash": AccountType.CASH, "kas": AccountType.CASH,
            "bank": AccountType.BANK,
            "ewallet": AccountType.EWALLET, "dompet": AccountType.EWALLET,
            "savings": AccountType.SAVINGS, "tabungan": AccountType.SAVINGS,
            "investment": AccountType.INVESTMENT, "investasi": AccountType.INVESTMENT,
        }
        acc_type = type_map.get(raw_type, AccountType.BANK)
        initial_balance = Decimal(str(args.get("initial_balance") or 0))

        acc = await self._svc.create_account(
            owner_jid=owner_jid,
            name=name,
            account_type=acc_type,
            initial_balance=initial_balance,
        )
        return json.dumps({
            "status": "success",
            "message": (
                f"Rekening '{acc.name}' ({acc.account_type.value}) berhasil dibuat "
                f"dengan saldo awal Rp {int(initial_balance):,}."
            ),
            "account_id": acc.id,
            "account_name": acc.name,
            "account_type": acc.account_type.value,
            "balance": float(acc.balance),
        }, ensure_ascii=False)

    # ── New handlers (Level 1 additions) ──────────────────────────────────────

    async def _get_accounts(self, owner_jid: str) -> str:
        accounts = await self._svc.get_accounts(owner_jid)
        return json.dumps({
            "status": "success",
            "count": len(accounts),
            "accounts": [
                {
                    "name": a.name,
                    "type": a.account_type.value,
                    "balance": float(a.balance),
                    "currency": a.currency,
                }
                for a in accounts
            ],
        }, ensure_ascii=False)

    async def _get_categories(self, owner_jid: str, args: dict) -> str:
        category_type: str | None = args.get("category_type")
        categories = await self._svc.get_categories(owner_jid, category_type=category_type)
        # Kelompokkan per tipe
        income_cats = [c for c in categories if c.category_type.value == "income"]
        expense_cats = [c for c in categories if c.category_type.value == "expense"]
        return json.dumps({
            "status": "success",
            "income_categories": [
                {"name": c.name, "icon": c.icon} for c in income_cats
            ],
            "expense_categories": [
                {"name": c.name, "icon": c.icon} for c in expense_cats
            ],
        }, ensure_ascii=False)

    async def _get_transaction_detail(self, owner_jid: str, args: dict) -> str:
        from datetime import datetime

        keyword: str | None = args.get("keyword")
        date_str: str | None = args.get("date")
        transaction_type: str | None = args.get("transaction_type")
        limit_val = args.get("limit")
        try:
            limit = min(int(limit_val), 10) if limit_val is not None else 5
        except (ValueError, TypeError):
            limit = 5

        date = None
        if date_str:
            try:
                date = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                pass

        transactions = await self._svc.search_transactions(
            owner_jid,
            keyword=keyword,
            date=date,
            transaction_type=transaction_type,
            limit=limit,
        )

        if not transactions:
            return json.dumps({
                "status": "not_found",
                "message": "Tidak ada transaksi yang cocok dengan kriteria pencarian.",
                "transactions": [],
            }, ensure_ascii=False)

        return json.dumps({
            "status": "success",
            "count": len(transactions),
            "transactions": [
                {
                    "transaction_id": tx.human_tx_id or tx.id,
                    "date": tx.transaction_date.strftime("%Y-%m-%d"),
                    "type": tx.transaction_type.value,
                    "amount": float(tx.amount),
                    "description": tx.description,
                    "category": tx.category_name,
                    "account": tx.account_name,
                }
                for tx in transactions
            ],
            "note": (
                "Gunakan transaction_id dari hasil ini untuk finance_update_transaction "
                "atau finance_delete_transaction."
            ) if len(transactions) > 1 else None,
        }, ensure_ascii=False)

    async def _update_transaction(self, owner_jid: str, args: dict) -> str:
        tx_id: str = args["transaction_id"]
        new_amount_raw = args.get("new_amount")
        new_amount = Decimal(str(new_amount_raw)) if new_amount_raw is not None else None

        # Resolve account name → account_id jika ada
        new_account_id = None
        new_account_name: str | None = args.get("new_account_name")
        if new_account_name:
            acc = await self._svc.find_account_by_name(owner_jid, new_account_name)
            if not acc:
                raise AccountNotFoundError(
                    f"Rekening '{new_account_name}' tidak ditemukan."
                )
            new_account_id = acc.id

        # Ambil transaksi lama untuk tahu jumlah aslinya
        orig_tx = await self._svc._repo.get_transaction_by_id(tx_id, owner_jid)
        if not orig_tx:
            from whatsapp_platform.features.finance.service import TransactionNotFoundError
            raise TransactionNotFoundError(f"Transaksi '{tx_id}' tidak ditemukan.")

        effective_amount = new_amount if new_amount is not None else orig_tx.amount

        corrected = await self._svc.correct_transaction(
            owner_jid=owner_jid,
            original_tx_id=tx_id,
            new_amount=effective_amount,
            new_description=args.get("new_description"),
            new_category_name=args.get("new_category_name"),
            new_account_id=new_account_id,
        )

        return json.dumps({
            "status": "success",
            "message": (
                f"Transaksi {orig_tx.human_tx_id or tx_id} berhasil diperbarui."
            ),
            "new_transaction_id": corrected.human_tx_id or corrected.id,
            "new_amount": float(corrected.amount),
            "new_description": corrected.description,
            "new_category": corrected.category_name,
            "new_account": corrected.account_name,
        }, ensure_ascii=False)

    async def _delete_transaction(self, owner_jid: str, args: dict) -> str:
        from whatsapp_platform.features.finance.service import (
            TransactionNotFoundError,
        )

        tx_id: str = args["transaction_id"]

        # Ambil detail dulu untuk pesan konfirmasi
        orig_tx = await self._svc._repo.get_transaction_by_id(tx_id, owner_jid)
        if not orig_tx:
            raise TransactionNotFoundError(f"Transaksi '{tx_id}' tidak ditemukan.")

        success = await self._svc.delete_transaction(owner_jid, tx_id)
        if success:
            return json.dumps({
                "status": "success",
                "message": (
                    f"Transaksi {orig_tx.human_tx_id or tx_id} "
                    f"({orig_tx.description or orig_tx.transaction_type.value}, "
                    f"Rp {int(orig_tx.amount):,}) berhasil dihapus."
                ),
                "deleted_transaction_id": orig_tx.human_tx_id or tx_id,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "status": "error",
                "error_code": "DELETE_FAILED",
                "message": f"Transaksi '{tx_id}' tidak dapat dihapus.",
            }, ensure_ascii=False)

    async def _create_budget(self, owner_jid: str, args: dict) -> str:
        category_name: str = args["category_name"]
        amount = Decimal(str(args["amount"]))
        month = args.get("month")
        year = args.get("year")

        progress = await self._svc.set_budget(
            owner_jid=owner_jid,
            category_name=category_name,
            amount=amount,
            month=int(month) if month is not None else None,
            year=int(year) if year is not None else None,
        )
        b = progress.budget
        return json.dumps({
            "status": "success",
            "message": f"Budget untuk kategori {b.category_name} sebesar Rp {int(b.amount):,} berhasil diatur.",
            "category": b.category_name,
            "amount": float(b.amount),
            "spent": float(progress.spent),
            "remaining": float(progress.remaining),
            "percentage": float(progress.percentage),
            "status_label": progress.status,
            "month": b.month,
            "year": b.year,
        }, ensure_ascii=False)

    async def _get_budget(self, owner_jid: str, args: dict) -> str:
        category_name: str = args["category_name"]
        month = args.get("month")
        year = args.get("year")

        progress = await self._svc.get_budget_progress(
            owner_jid=owner_jid,
            category_name=category_name,
            month=int(month) if month is not None else None,
            year=int(year) if year is not None else None,
        )
        if not progress:
            return json.dumps({
                "status": "not_found",
                "message": f"Belum ada budget untuk kategori '{category_name}'.",
                "category": category_name,
            }, ensure_ascii=False)

        b = progress.budget
        return json.dumps({
            "status": "success",
            "category": b.category_name,
            "amount": float(b.amount),
            "spent": float(progress.spent),
            "remaining": float(progress.remaining),
            "percentage": float(progress.percentage),
            "status_label": progress.status,
            "month": b.month,
            "year": b.year,
        }, ensure_ascii=False)

    async def _list_budgets(self, owner_jid: str, args: dict) -> str:
        month = args.get("month")
        year = args.get("year")

        budgets = await self._svc.list_budgets(
            owner_jid=owner_jid,
            month=int(month) if month is not None else None,
            year=int(year) if year is not None else None,
        )
        return json.dumps({
            "status": "success",
            "count": len(budgets),
            "budgets": [
                {
                    "category": p.budget.category_name,
                    "icon": p.budget.category_icon,
                    "amount": float(p.budget.amount),
                    "spent": float(p.spent),
                    "remaining": float(p.remaining),
                    "percentage": float(p.percentage),
                    "status_label": p.status,
                    "month": p.budget.month,
                    "year": p.budget.year,
                }
                for p in budgets
            ],
        }, ensure_ascii=False)

    async def _delete_budget(self, owner_jid: str, args: dict) -> str:
        category_name: str = args["category_name"]
        month = args.get("month")
        year = args.get("year")

        await self._svc.delete_budget(
            owner_jid=owner_jid,
            category_name=category_name,
            month=int(month) if month is not None else None,
            year=int(year) if year is not None else None,
        )
        return json.dumps({
            "status": "success",
            "message": f"Budget untuk kategori '{category_name}' berhasil dihapus.",
            "category": category_name,
        }, ensure_ascii=False)

