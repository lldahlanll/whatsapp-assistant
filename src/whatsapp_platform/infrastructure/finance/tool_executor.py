"""FinanceToolExecutor — dispatches LLM finance tool calls to FinanceService."""

from __future__ import annotations

import hashlib
import json
import re
import time
from contextvars import ContextVar
from datetime import datetime, timedelta
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
from whatsapp_platform.shared.utils.timezone import (
    day_bounds_utc,
    now_local,
    parse_local_date,
    parse_local_datetime,
    to_local,
)

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID
    from whatsapp_platform.features.finance.service import FinanceService

logger = structlog.get_logger()


# Konfirmasi aksi destruktif harus datang dari pesan user berikutnya, bukan dari LLM di giliran yang sama.
_CONFIRMATION_TTL_SECONDS = 300.0
_TRUTHY = {"true", "1", "ya", "iya", "yes", "y"}


_AFFIRMATIVE_WORDS = frozenset({
    "ya", "iya", "iyaa", "y", "yes", "yup", "ok", "oke", "okay", "okey", "lanjut", "lanjutkan",
    "yakin", "setuju", "benar", "betul", "hapus", "reset", "gas", "silakan", "silahkan",
})
_NEGATION_WORDS = frozenset({
    "jangan", "tidak", "nggak", "ngga", "gak", "ga", "enggak", "bukan", "batal", "batalkan",
    "cancel", "no", "tunggu", "stop", "belum", "tapi", "kenapa", "apa", "gimana", "bagaimana",
})
_MAX_AFFIRMATION_WORDS = 6

# Teks pesan user yang sedang diproses; diisi oleh execute() agar konfirmasi bisa diverifikasi di server.
_current_user_text: ContextVar[str | None] = ContextVar("finance_current_user_text", default=None)


def is_affirmative(text: str | None) -> bool:
    """True jika pesan user singkat dan jelas menyetujui ("ya", "iya hapus", "ok lanjut").

    Fail closed: teks kosong/None, terlalu panjang, berisi penolakan atau pertanyaan -> False.
    """
    if not text:
        return False
    if "?" in text:
        return False
    words = re.findall(r"[a-z]+", text.lower())
    if not words or len(words) > _MAX_AFFIRMATION_WORDS:
        return False
    if any(w in _NEGATION_WORDS for w in words):
        return False
    return words[0] in _AFFIRMATIVE_WORDS


def _as_bool(value: Any) -> bool:
    """bool("false") == True, jadi parse string dari LLM secara eksplisit."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _idempotency_key(message_id: str | None, tool_name: str, args: dict) -> str | None:
    """Kunci anti-dobel dari ID pesan WhatsApp + isi transaksi.

    Pesan yang sama diproses ulang (event ganda, retry) → kunci sama → tidak tercatat dua kali.
    Dua transaksi berbeda dalam satu pesan ("kopi 20rb dan roti 15rb") → kunci berbeda.
    """
    if not message_id:
        return None
    payload = {k: v for k, v in sorted(args.items()) if k != "idempotency_key"}
    digest = hashlib.sha256(
        json.dumps([tool_name, payload], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"wa:{message_id[:64]}:{digest}"


GROUP_BLOCKED_TOOLS: set[str] = {
    "finance_get_balance",
    "finance_get_monthly_report",
    "finance_get_transactions",
    "finance_get_expense_summary",
    "finance_create_account",
    "finance_delete_account",
    "finance_get_accounts",
    "finance_get_categories",
    "finance_get_transaction_detail",
    "finance_update_transaction",
    "finance_delete_transaction",
    "finance_create_budget",
    "finance_get_budget",
    "finance_list_budgets",
    "finance_delete_budget",
    "finance_reset_data",
}


class FinanceToolExecutor:
    def __init__(self, finance_service: FinanceService) -> None:
        self._svc = finance_service
        # (owner, action, target) -> (message_id yang meminta konfirmasi, waktu)
        self._pending_confirmations: dict[tuple[str, str, str], tuple[str, float]] = {}

    def _confirmed_by_user(
        self, owner_jid: str, action: str, target: str, message_id: str | None, confirm: Any
    ) -> bool:
        """True hanya jika konfirmasi datang di pesan user SETELAH permintaan konfirmasi.

        Panggilan pertama (atau confirm dari giliran yang sama) mendaftarkan permintaan
        konfirmasi dan mengembalikan False, sehingga LLM tidak bisa mengonfirmasi sendiri.
        Selain flag dari LLM, teks pesan user itu sendiri harus berupa persetujuan eksplisit
        (lihat ``is_affirmative``); flag ``confirm`` saja tidak cukup.
        """
        key = (owner_jid, action, target)
        now = time.monotonic()
        pending = self._pending_confirmations.get(key)
        if (
            _as_bool(confirm)
            and message_id
            and pending is not None
            and pending[0] != message_id
            and now - pending[1] <= _CONFIRMATION_TTL_SECONDS
            and is_affirmative(_current_user_text.get())
        ):
            del self._pending_confirmations[key]
            return True
        if message_id:
            self._pending_confirmations[key] = (message_id, now)
        return False

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
        message_id: str | None = None,
        user_text: str | None = None,
    ) -> str:
        token = _current_user_text.set(user_text)
        try:
            return await self._execute(tool_name, arguments, user_jid, chat_jid, message_id)
        finally:
            _current_user_text.reset(token)

    async def _execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
        message_id: str | None = None,
    ) -> str:
        owner_jid = str(user_jid)
        is_group = False
        if hasattr(chat_jid, "is_group"):
            is_group = bool(chat_jid.is_group)
        elif isinstance(chat_jid, str) and chat_jid.endswith("@g.us"):
            is_group = True

        logger.info(
            "Executing finance tool call",
            tool=tool_name,
            argument_names=sorted(arguments),
            owner=owner_jid,
            is_group=is_group,
        )
        logger.debug("Finance tool call arguments", tool=tool_name, arguments=arguments)

        if is_group and tool_name in GROUP_BLOCKED_TOOLS:
            logger.info("Blocked finance tool in group chat", tool=tool_name, owner=owner_jid)
            return json.dumps({
                "status": "error",
                "error_code": "GROUP_PRIVATE_ONLY",
                "message": "Data keuangan pribadi hanya dapat dilihat di chat private. Silakan hubungi saya lewat chat pribadi.",
            }, ensure_ascii=False)

        try:
            if tool_name == "finance_add_income":
                result = await self._add_income(owner_jid, arguments, message_id)

            elif tool_name == "finance_add_expense":
                result = await self._add_expense(owner_jid, arguments, message_id)

            elif tool_name == "finance_transfer":
                result = await self._transfer(owner_jid, arguments, message_id)

            elif tool_name == "finance_get_balance":
                result = await self._get_balance(owner_jid)

            elif tool_name == "finance_get_monthly_report":
                result = await self._get_monthly_report(owner_jid, arguments)

            elif tool_name == "finance_get_transactions":
                result = await self._get_transactions(owner_jid, arguments)

            elif tool_name == "finance_get_expense_summary":
                result = await self._get_expense_summary(owner_jid, arguments)

            elif tool_name == "finance_create_account":
                result = await self._create_account(owner_jid, arguments)

            elif tool_name == "finance_delete_account":
                result = await self._delete_account(owner_jid, arguments, message_id)

            elif tool_name == "finance_get_accounts":
                result = await self._get_accounts(owner_jid)

            elif tool_name == "finance_get_categories":
                result = await self._get_categories(owner_jid, arguments)

            elif tool_name == "finance_get_transaction_detail":
                result = await self._get_transaction_detail(owner_jid, arguments)

            elif tool_name == "finance_update_transaction":
                result = await self._update_transaction(owner_jid, arguments)

            elif tool_name == "finance_delete_transaction":
                result = await self._delete_transaction(owner_jid, arguments, message_id)

            elif tool_name == "finance_create_budget":
                result = await self._create_budget(owner_jid, arguments)

            elif tool_name == "finance_get_budget":
                result = await self._get_budget(owner_jid, arguments)

            elif tool_name == "finance_list_budgets":
                result = await self._list_budgets(owner_jid, arguments)

            elif tool_name == "finance_delete_budget":
                result = await self._delete_budget(owner_jid, arguments)

            elif tool_name == "finance_reset_data":
                result = await self._reset_data(owner_jid, arguments, message_id)

            else:
                return json.dumps({
                    "status": "error",
                    "error_code": "INVALID_TOOL",
                    "message": f"Tool '{tool_name}' tidak dikenali.",
                }, ensure_ascii=False)

            if is_group:
                try:
                    data = json.loads(result)
                    if isinstance(data, dict):
                        data.pop("new_balance", None)
                        data.pop("balance", None)
                        data.pop("from_new_balance", None)
                        data.pop("to_new_balance", None)
                        if isinstance(data.get("transaction"), dict):
                            data["transaction"].pop("new_balance", None)
                            data["transaction"].pop("balance", None)
                            data["transaction"].pop("from_new_balance", None)
                            data["transaction"].pop("to_new_balance", None)
                        result = json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass

            return result

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
                # Pesan asli memuat nominal saldo; jangan bocorkan di grup.
                "message": (
                    "Saldo rekening tidak mencukupi. Cek detail saldo lewat chat pribadi."
                    if is_group
                    else str(exc)
                ),
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
        """Tanggal dari LLM dalam waktu lokal. Hari ini → None agar memakai jam sekarang."""
        dt = parse_local_datetime(val)
        if dt is None:
            return None
        if "T" not in val and to_local(dt).date() == now_local().date():
            return None
        return dt

    async def _add_income(self, owner_jid: str, args: dict, message_id: str | None = None) -> str:
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
            idempotency_key=_idempotency_key(message_id, "finance_add_income", args),
        )
        current_acc = await self._svc._repo.get_account_by_id(tx.account_id, owner_jid)
        date_str = (
            to_local(tx.transaction_date).strftime("%Y-%m-%d")
            if tx.transaction_date
            else now_local().strftime("%Y-%m-%d")
        )
        return json.dumps({
            "status": "success",
            "transaction_id": tx.human_tx_id or tx.id,
            "date": date_str,
            "type": "income",
            "amount": float(amount),
            "account_name": tx.account_name,
            "category": tx.category_name,
            "category_name": tx.category_name,
            "description": tx.description,
            "new_balance": float(current_acc.balance) if current_acc else None,
            "message": (
                f"Pemasukan Rp {int(amount):,} berhasil dicatat ke {tx.account_name}."
            ),
        }, ensure_ascii=False)

    async def _add_expense(self, owner_jid: str, args: dict, message_id: str | None = None) -> str:
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
            idempotency_key=_idempotency_key(message_id, "finance_add_expense", args),
        )
        current_acc = await self._svc._repo.get_account_by_id(tx.account_id, owner_jid)
        date_str = (
            to_local(tx.transaction_date).strftime("%Y-%m-%d")
            if tx.transaction_date
            else now_local().strftime("%Y-%m-%d")
        )
        return json.dumps({
            "status": "success",
            "transaction_id": tx.human_tx_id or tx.id,
            "date": date_str,
            "type": "expense",
            "amount": float(amount),
            "account_name": tx.account_name,
            "category": tx.category_name,
            "category_name": tx.category_name,
            "description": tx.description,
            "new_balance": float(current_acc.balance) if current_acc else None,
            "message": (
                f"Pengeluaran Rp {int(amount):,} dari {tx.account_name} berhasil dicatat."
            ),
        }, ensure_ascii=False)

    async def _transfer(self, owner_jid: str, args: dict, message_id: str | None = None) -> str:
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
            idempotency_key=_idempotency_key(message_id, "finance_transfer", args),
        )
        updated_from = await self._svc._repo.get_account_by_id(from_acc.id, owner_jid)
        updated_to = await self._svc._repo.get_account_by_id(to_acc.id, owner_jid)
        date_str = (
            to_local(tx.transaction_date).strftime("%Y-%m-%d")
            if tx.transaction_date
            else now_local().strftime("%Y-%m-%d")
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
            "available_balance": float(data.get("available_balance", data["total"])),
            "investment_balance": float(data.get("investment_balance", 0)),
            "currency": "IDR",
            "accounts": [
                {
                    "name": a["name"],
                    "balance": float(a["balance"]),
                    "type": a["type"],
                    "classification": a.get("classification", "available"),
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

        # date_from / date_to adalah tanggal lokal; date_to inklusif sampai akhir hari.
        day_from = parse_local_date(args.get("date_from"))
        day_to = parse_local_date(args.get("date_to"))
        date_from = day_bounds_utc(day_from)[0] if day_from else None
        date_to = day_bounds_utc(day_to)[1] - timedelta(microseconds=1) if day_to else None
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
                    "date": to_local(tx.transaction_date).strftime("%Y-%m-%d"),
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
            "cash": AccountType.CASH, "kas": AccountType.CASH, "tunai": AccountType.CASH, "fisik": AccountType.CASH,
            "bank": AccountType.BANK,
            "ewallet": AccountType.EWALLET, "dompet": AccountType.EWALLET,
            "savings": AccountType.SAVINGS, "tabungan": AccountType.SAVINGS,
            "deposit": AccountType.DEPOSIT, "deposito": AccountType.DEPOSIT,
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

    async def _delete_account(self, owner_jid: str, args: dict, message_id: str | None = None) -> str:
        name: str = args["name"]

        acc = await self._svc.find_account_by_name(owner_jid, name)
        if not acc:
            acc = await self._svc._repo.get_account_by_id(name, owner_jid)

        if not acc:
            raise AccountNotFoundError(f"Rekening '{name}' tidak ditemukan.")

        if not self._confirmed_by_user(owner_jid, "delete_account", acc.id, message_id, args.get("confirm")):
            return json.dumps({
                "status": "need_confirmation",
                "account_name": acc.name,
                "account_type": acc.account_type.value,
                "balance": float(acc.balance),
                "message": (
                    f"Rekening '{acc.name}' ({acc.account_type.value}) memiliki sisa saldo "
                    f"Rp {int(acc.balance):,}. Apakah Anda yakin ingin menghapusnya? "
                    "Tanyakan konfirmasi kepada pengguna sebelum memanggil tool ini dengan confirm=true."
                ),
            }, ensure_ascii=False)

        deleted = await self._svc.delete_account(owner_jid, acc.id)
        return json.dumps({
            "status": "success",
            "message": f"Rekening '{deleted.name}' berhasil dihapus/dinonaktifkan.",
            "account_name": deleted.name,
            "balance": float(deleted.balance),
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

        keyword: str | None = args.get("keyword")
        date_str: str | None = args.get("date")
        transaction_type: str | None = args.get("transaction_type")
        limit_val = args.get("limit")
        try:
            limit = min(int(limit_val), 10) if limit_val is not None else 5
        except (ValueError, TypeError):
            limit = 5

        date = parse_local_date(date_str)

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
                    "date": to_local(tx.transaction_date).strftime("%Y-%m-%d"),
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
        tx_id: str = args.get("transaction_id") or args.get("tx_id") or args.get("id", "")
        if not tx_id:
            return json.dumps({
                "status": "error",
                "error_code": "INVALID_ARGUMENT",
                "message": "Parameter transaction_id wajib diisi.",
            }, ensure_ascii=False)

        # Parse amount flexibly
        new_amount_raw = (
            args.get("new_amount")
            if args.get("new_amount") is not None
            else args.get("amount")
        )
        if new_amount_raw is None:
            new_amount_raw = args.get("nominal")

        new_amount = None
        if new_amount_raw is not None:
            if isinstance(new_amount_raw, (int, float, Decimal)):
                new_amount = Decimal(str(new_amount_raw))
            else:
                s = str(new_amount_raw).strip()
                from whatsapp_platform.features.finance.parser import parse_amount_from_text
                parsed = parse_amount_from_text(s)
                if parsed is not None:
                    new_amount = parsed
                else:
                    clean = s.replace(".", "").replace(",", "").replace("Rp", "").replace("rp", "").strip()
                    try:
                        new_amount = Decimal(clean)
                    except Exception:
                        new_amount = Decimal(s)

        # Resolve account name → account_id jika ada
        new_account_id = None
        new_account_name: str | None = (
            args.get("new_account_name")
            or args.get("account_name")
            or args.get("account")
        )
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
            # Fallback jika tx_id berupa keyword / deskripsi pencarian
            matches = await self._svc.search_transactions(owner_jid, keyword=tx_id, limit=2)
            if len(matches) == 1:
                orig_tx = matches[0]
                tx_id = orig_tx.id
            elif len(matches) > 1:
                return json.dumps({
                    "status": "error",
                    "error_code": "AMBIGUOUS_TRANSACTION",
                    "message": (
                        f"Ditemukan {len(matches)} transaksi dengan kata kunci '{tx_id}'. "
                        f"Sebutkan ID transaksi yang ingin diubah (contoh: {matches[0].human_tx_id})."
                    ),
                }, ensure_ascii=False)
            else:
                from whatsapp_platform.features.finance.service import TransactionNotFoundError
                raise TransactionNotFoundError(f"Transaksi '{tx_id}' tidak ditemukan.")

        effective_amount = new_amount if new_amount is not None else orig_tx.amount

        new_description = (
            args.get("new_description")
            if args.get("new_description") is not None
            else args.get("description")
        )
        if new_description is None:
            new_description = args.get("desc")

        new_category_name = (
            args.get("new_category_name")
            if args.get("new_category_name") is not None
            else args.get("category_name")
        )
        if new_category_name is None:
            new_category_name = args.get("category")

        corrected = await self._svc.correct_transaction(
            owner_jid=owner_jid,
            original_tx_id=tx_id,
            new_amount=effective_amount,
            new_description=new_description,
            new_category_name=new_category_name,
            new_account_id=new_account_id,
        )

        return json.dumps({
            "status": "success",
            "message": (
                f"Transaksi {orig_tx.human_tx_id or tx_id} berhasil diperbarui."
            ),
            "transaction_id": corrected.human_tx_id or corrected.id,
            "new_transaction_id": corrected.human_tx_id or corrected.id,
            "new_amount": float(corrected.amount),
            "amount": float(corrected.amount),
            "new_description": corrected.description,
            "description": corrected.description,
            "new_category": corrected.category_name,
            "category": corrected.category_name,
            "new_account": corrected.account_name,
            "account": corrected.account_name,
        }, ensure_ascii=False)

    async def _delete_transaction(self, owner_jid: str, args: dict, message_id: str | None = None) -> str:
        from whatsapp_platform.features.finance.service import (
            TransactionNotFoundError,
        )

        tx_id: str = args.get("transaction_id") or args.get("tx_id") or args.get("id", "")
        if not tx_id:
            return json.dumps({
                "status": "error",
                "error_code": "INVALID_ARGUMENT",
                "message": "Parameter transaction_id wajib diisi.",
            }, ensure_ascii=False)

        # Ambil detail dulu untuk pesan konfirmasi
        orig_tx = await self._svc._repo.get_transaction_by_id(tx_id, owner_jid)
        if not orig_tx:
            matches = await self._svc.search_transactions(owner_jid, keyword=tx_id, limit=2)
            if len(matches) == 1:
                orig_tx = matches[0]
                tx_id = orig_tx.id
            elif len(matches) > 1:
                return json.dumps({
                    "status": "error",
                    "error_code": "AMBIGUOUS_TRANSACTION",
                    "message": (
                        f"Ditemukan {len(matches)} transaksi dengan kata kunci '{tx_id}'. "
                        f"Sebutkan ID transaksi yang ingin dihapus (contoh: {matches[0].human_tx_id})."
                    ),
                }, ensure_ascii=False)
            else:
                raise TransactionNotFoundError(f"Transaksi '{tx_id}' tidak ditemukan.")

        tx_label = orig_tx.human_tx_id or tx_id
        if not self._confirmed_by_user(owner_jid, "delete_transaction", orig_tx.id, message_id, args.get("confirm")):
            return json.dumps({
                "status": "need_confirmation",
                "transaction_id": tx_label,
                "transaction_type": orig_tx.transaction_type.value,
                "description": orig_tx.description,
                "amount": float(orig_tx.amount),
                "account": orig_tx.account_name,
                "message": (
                    f"Transaksi {tx_label} ({orig_tx.description or orig_tx.transaction_type.value}, "
                    f"Rp {int(orig_tx.amount):,}) akan dihapus dan saldo rekening dikembalikan. "
                    "Tanyakan konfirmasi kepada pengguna sebelum memanggil tool ini dengan confirm=true."
                ),
            }, ensure_ascii=False)

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

    async def _delete_budget(self, owner_jid: str, arguments: dict) -> str:
        import calendar
        now = now_local()

        category_name: str = arguments.get("category_name", "")
        month: int = int(arguments.get("month") or now.month)
        year: int = int(arguments.get("year") or now.year)

        await self._svc.delete_budget(owner_jid, category_name, month=month, year=year)
        month_name = calendar.month_name[month]
        return json.dumps(
            {
                "status": "success",
                "message": f"Budget kategori '{category_name}' untuk {month_name} {year} berhasil dihapus.",
            },
            ensure_ascii=False,
        )

    async def _reset_data(self, owner_jid: str, arguments: dict, message_id: str | None = None) -> str:
        """Preview atau eksekusi reset semua data finance user."""
        if not self._confirmed_by_user(owner_jid, "reset_data", "all", message_id, arguments.get("confirm")):
            # Preview saja — tidak menghapus
            preview = await self._svc.get_reset_preview(owner_jid)
            return json.dumps(
                {
                    "status": "preview",
                    "message": (
                        "Preview data yang akan dihapus jika reset dikonfirmasi. "
                        "Belum ada yang dihapus."
                    ),
                    "data": {
                        "accounts": preview["accounts"],
                        "transactions": preview["transactions"],
                        "budgets": preview["budgets"],
                        "categories": preview["categories"],
                    },
                    "next_step": (
                        "Sampaikan ringkasan ini ke pengguna dan minta konfirmasi eksplisit. "
                        "Jika dikonfirmasi, panggil finance_reset_data dengan confirm=True."
                    ),
                },
                ensure_ascii=False,
            )

        # Eksekusi reset
        counts = await self._svc.reset_all_data(owner_jid)
        return json.dumps(
            {
                "status": "success",
                "message": "Semua data finance berhasil direset ke kondisi nol bersih.",
                "deleted": {
                    "accounts": counts.get("accounts", 0),
                    "transactions": counts.get("transactions", 0),
                    "budgets": counts.get("budgets", 0),
                    "categories": counts.get("categories", 0),
                },
            },
            ensure_ascii=False,
        )
