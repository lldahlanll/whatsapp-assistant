"""Finance Structured Action & Fast-Path Confirmation Generator.

Validates deterministic finance mutations (add expense, add income, transfer)
and formats local confirmation responses, avoiding an unnecessary second LLM call.

Also handles all read-only query tools and other mutation results so that
the agentic loop returns after exactly 1 LLM call in most cases.
"""

from __future__ import annotations

import json

# ── Mutation tools (original fast-path) ───────────────────────────────────────

MUTATION_TOOLS: set[str] = {
    "finance_add_expense",
    "finance_add_income",
    "finance_transfer",
}

# ── All tools with local fast-path handlers ────────────────────────────────────

_FAST_PATH_HANDLERS: dict[str, "_HandlerFn"] = {}  # filled below via decorator

from typing import Callable
_HandlerFn = Callable[[dict], str | None]


def _handler(tool_name: str):
    """Decorator to register a fast-path handler for a tool."""
    def decorator(fn: _HandlerFn) -> _HandlerFn:
        _FAST_PATH_HANDLERS[tool_name] = fn
        return fn
    return decorator


def _fmt_rp(amount) -> str:
    """Format angka ke format Rupiah Indonesia."""
    try:
        return f"Rp {int(amount):,}".replace(",", ".")
    except (TypeError, ValueError):
        return f"Rp {amount}"


# ── Handlers ──────────────────────────────────────────────────────────────────


@_handler("finance_add_expense")
def _fast_add_expense(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status not in ("success", "ok"):
        return None
    if data.get("error") or data.get("code") in ("ACCOUNT_REQUIRED", "ACCOUNT_NOT_FOUND"):
        return None

    tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
    amount = tx.get("amount") or data.get("amount")
    if amount is None:
        return None

    account = tx.get("account_name") or data.get("account_name") or "Kas"
    category = tx.get("category_name") or data.get("category_name") or "-"
    desc = tx.get("description") or data.get("description") or "-"
    new_balance = data.get("new_balance") or data.get("balance")
    date = tx.get("date") or data.get("date")

    balance_str = f"\n• Saldo Terkini: {_fmt_rp(new_balance)}" if new_balance is not None else ""
    date_line = f"• Tanggal: {date}\n" if date else ""

    return (
        f"*Pengeluaran Dicatat*\n\n"
        f"• Jumlah: {_fmt_rp(amount)}\n"
        f"{date_line}"
        f"• Kategori: {category}\n"
        f"• Rekening: {account}\n"
        f"• Catatan: {desc}"
        f"{balance_str}"
    )


@_handler("finance_add_income")
def _fast_add_income(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status not in ("success", "ok"):
        return None
    if data.get("error") or data.get("code") in ("ACCOUNT_REQUIRED", "ACCOUNT_NOT_FOUND"):
        return None

    tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
    amount = tx.get("amount") or data.get("amount")
    if amount is None:
        return None

    account = tx.get("account_name") or data.get("account_name") or "Kas"
    category = tx.get("category_name") or data.get("category_name") or "-"
    desc = tx.get("description") or data.get("description") or "-"
    new_balance = data.get("new_balance") or data.get("balance")
    date = tx.get("date") or data.get("date")

    balance_str = f"\n• Saldo Terkini: {_fmt_rp(new_balance)}" if new_balance is not None else ""
    date_line = f"• Tanggal: {date}\n" if date else ""

    return (
        f"*Pemasukan Dicatat*\n\n"
        f"• Jumlah: {_fmt_rp(amount)}\n"
        f"{date_line}"
        f"• Kategori: {category}\n"
        f"• Rekening: {account}\n"
        f"• Catatan: {desc}"
        f"{balance_str}"
    )


@_handler("finance_transfer")
def _fast_transfer(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status not in ("success", "ok"):
        return None
    if data.get("error") or data.get("code") in ("ACCOUNT_REQUIRED", "ACCOUNT_NOT_FOUND"):
        return None

    tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
    amount = tx.get("amount") or data.get("amount")
    if amount is None:
        return None

    from_acc = tx.get("from_account_name") or data.get("from_account_name") or "-"
    to_acc = tx.get("to_account_name") or data.get("to_account_name") or "-"
    desc = tx.get("description") or data.get("description") or "-"
    new_balance = data.get("new_balance") or data.get("balance")
    date = tx.get("date") or data.get("date")

    balance_str = f"\n• Saldo Terkini: {_fmt_rp(new_balance)}" if new_balance is not None else ""
    date_line = f"• Tanggal: {date}\n" if date else ""

    return (
        f"*Transfer Berhasil*\n\n"
        f"• Jumlah: {_fmt_rp(amount)}\n"
        f"{date_line}"
        f"• Dari Rekening: {from_acc}\n"
        f"• Ke Rekening: {to_acc}\n"
        f"• Catatan: {desc}"
        f"{balance_str}"
    )


@_handler("finance_get_transactions")
def _fast_get_transactions(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status == "not_found" or not data.get("transactions"):
        return "Belum ada transaksi yang tercatat."

    if status != "success":
        return None

    transactions = data.get("transactions", [])
    if not transactions:
        return "Belum ada transaksi yang tercatat."

    lines = ["*Riwayat Transaksi*\n"]
    for i, tx in enumerate(transactions, 1):
        amount = _fmt_rp(tx.get("amount", 0))
        desc = tx.get("description") or tx.get("category") or tx.get("type", "")
        date = tx.get("date", "")
        account = tx.get("account") or ""
        tx_id = tx.get("transaction_id", "")

        line = f"{i}. *{amount}* — {desc}"
        if date:
            line += f"\n   Tanggal: {date}"
        if account:
            line += f" • {account}"
        if tx_id:
            line += f"\n   ID: `{tx_id}`"
        lines.append(line)

    return "\n".join(lines)


@_handler("finance_get_balance")
def _fast_get_balance(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    accounts = data.get("accounts", [])
    if not accounts:
        return "Belum ada rekening aktif. Buat rekening dulu ya."

    lines = ["*Saldo Rekening*\n"]
    total = 0.0
    for acc in accounts:
        balance = acc.get("balance", 0)
        total += float(balance)
        lines.append(f"• *{acc.get('name')}* — {_fmt_rp(balance)}")

    if len(accounts) > 1:
        lines.append(f"\n*Total: {_fmt_rp(total)}*")

    return "\n".join(lines)


@_handler("finance_get_accounts")
def _fast_get_accounts(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    accounts = data.get("accounts", [])
    if not accounts:
        return "Belum ada rekening aktif. Buat rekening dulu ya."

    lines = [f"*Daftar Rekening* ({len(accounts)} rekening)\n"]
    for acc in accounts:
        acc_type = (acc.get("type") or "bank").lower()
        lines.append(f"• *{acc.get('name')}* ({acc_type}) — {_fmt_rp(acc.get('balance', 0))}")

    return "\n".join(lines)


@_handler("finance_get_monthly_report")
def _fast_get_monthly_report(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    month = data.get("month", "")
    year = data.get("year", "")
    income = data.get("total_income", 0)
    expense = data.get("total_expense", 0)
    net = data.get("net", 0)

    MONTH_NAMES = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember",
    }
    month_name = MONTH_NAMES.get(int(month), str(month)) if month else ""
    period = f"{month_name} {year}" if month_name else str(year)

    net_str = _fmt_rp(abs(net))
    net_label = f"Surplus: {net_str}" if float(net) >= 0 else f"Defisit: {net_str}"

    lines = [
        f"*Laporan {period}*\n",
        f"Pemasukan: {_fmt_rp(income)}",
        f"Pengeluaran: {_fmt_rp(expense)}",
        f"{net_label}",
    ]

    top_cats = data.get("top_expense_categories", [])
    if top_cats:
        lines.append("\n*Top Pengeluaran:*")
        for c in top_cats[:5]:
            lines.append(f"  • {c.get('name')} — {_fmt_rp(c.get('total', 0))} ({c.get('count', 0)}x)")

    return "\n".join(lines)


@_handler("finance_get_expense_summary")
def _fast_get_expense_summary(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    cats = data.get("expense_by_category", [])
    if not cats:
        return "Belum ada data pengeluaran untuk periode ini."

    total = sum(float(c.get("total", 0)) for c in cats)
    lines = [f"*Ringkasan Pengeluaran*\n"]
    for c in cats:
        amount = float(c.get("total", 0))
        pct = (amount / total * 100) if total > 0 else 0
        lines.append(f"• *{c.get('name')}* — {_fmt_rp(amount)} ({pct:.0f}%)")

    lines.append(f"\n*Total: {_fmt_rp(total)}*")
    return "\n".join(lines)


@_handler("finance_create_account")
def _fast_create_account(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    name = data.get("account_name", "")
    acc_type = data.get("account_type", "bank")
    balance = data.get("balance", 0)

    return (
        f"*Rekening Berhasil Dibuat!*\n\n"
        f"Nama: {name}\n"
        f"Tipe: {acc_type}\n"
        f"Saldo Awal: {_fmt_rp(balance)}"
    )


@_handler("finance_delete_account")
def _fast_delete_account(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()

    if status == "need_confirmation":
        name = data.get("account_name", "")
        acc_type = data.get("account_type", "")
        balance = data.get("balance", 0)
        return (
            f"*Konfirmasi Hapus Rekening*\n\n"
            f"Nama: {name}\n"
            f"Tipe: {acc_type}\n"
            f"Sisa Saldo: {_fmt_rp(balance)}\n\n"
            f"Rekening ini akan dinonaktifkan. Yakin ingin menghapusnya?"
        )

    if status == "success":
        name = data.get("account_name", "")
        balance = data.get("balance", 0)
        return (
            f"*Rekening Berhasil Dihapus*\n\n"
            f"{name} (Saldo terakhir: {_fmt_rp(balance)}) sudah dinonaktifkan."
        )

    return None


@_handler("finance_delete_transaction")
def _fast_delete_transaction(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    tx_id = data.get("deleted_transaction_id", "")
    msg = data.get("message", f"Transaksi {tx_id} berhasil dihapus.")
    return msg


@_handler("finance_delete_budget")
def _fast_delete_budget(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    category = data.get("category", "")
    return f"Budget untuk kategori *{category}* berhasil dihapus."


@_handler("finance_list_budgets")
def _fast_list_budgets(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    budgets = data.get("budgets", [])
    if not budgets:
        return "Belum ada budget yang diatur. Set budget dengan menyebutkan kategori dan jumlahnya."

    lines = [f"*Daftar Budget* ({len(budgets)} kategori)\n"]
    for b in budgets:
        cat = b.get("category", "")
        amount = b.get("amount", 0)
        spent = b.get("spent", 0)
        remaining = b.get("remaining", 0)
        pct = b.get("percentage", 0)
        status_label = b.get("status_label", "")
        month = b.get("month", "")
        year = b.get("year", "")

        lines.append(
            f"• *{cat}* ({month}/{year})\n"
            f"  Terpakai: {_fmt_rp(spent)} / {_fmt_rp(amount)} ({float(pct):.0f}%)\n"
            f"  Sisa: {_fmt_rp(remaining)} — {status_label}"
        )

    return "\n".join(lines)


@_handler("finance_get_budget")
def _fast_get_budget(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()

    if status == "not_found":
        category = data.get("category", "")
        return f"Belum ada budget untuk kategori *{category}*. Set dulu ya."

    if status != "success":
        return None

    cat = data.get("category", "")
    amount = data.get("amount", 0)
    spent = data.get("spent", 0)
    remaining = data.get("remaining", 0)
    pct = float(data.get("percentage", 0))
    status_label = data.get("status_label", "")
    month = data.get("month", "")
    year = data.get("year", "")

    return (
        f"*Budget {cat}* ({month}/{year})\n\n"
        f"• Anggaran: {_fmt_rp(amount)}\n"
        f"• Terpakai: {_fmt_rp(spent)} ({pct:.0f}%)\n"
        f"• Sisa: {_fmt_rp(remaining)}\n"
        f"• Status: {status_label}"
    )


# ── Public API ─────────────────────────────────────────────────────────────────


def try_finance_mutation_fast_path(tool_name: str, raw_tool_result: str) -> str | None:
    """Attempt fast-path confirmation template generation.

    Covers both mutation tools and all read-only query tools to eliminate
    the second LLM call in the agentic tool-calling loop.

    Args:
        tool_name: Name of tool executed.
        raw_tool_result: Output JSON string from tool executor.

    Returns:
        Formatted WhatsApp text confirmation if successful, or None to fall back to LLM Call 2.
    """
    if not raw_tool_result:
        return None

    handler = _FAST_PATH_HANDLERS.get(tool_name)
    if handler is None:
        return None

    try:
        data = json.loads(raw_tool_result)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    try:
        return handler(data)
    except Exception:
        return None
