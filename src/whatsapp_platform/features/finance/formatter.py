"""Finance output formatter — menghasilkan teks siap kirim ke WhatsApp."""

from __future__ import annotations

import calendar
from decimal import Decimal

from whatsapp_platform.domain.entities.finance import (
    BudgetProgress,
    FinanceAccount,
    FinanceTransaction,
    MonthlySummary,
    TransactionType,
)


def _fmt(amount: Decimal) -> str:
    """Format angka ke Rp 1.500.000."""
    return f"Rp {int(amount):,}".replace(",", ".")


def format_balance(data: dict) -> str:
    accounts: list[dict] = data.get("accounts", [])
    total: Decimal = data.get("total", Decimal("0"))

    lines = ["*Saldo Rekening*", "━━━━━━━━━━━━━━━━━━"]
    for acc in accounts:
        lines.append(f"• *{acc['name']}*: {_fmt(acc['balance'])}")

    lines += ["━━━━━━━━━━━━━━━━━━", f"*Total: {_fmt(total)}*"]
    return "\n".join(lines)


def format_transaction_added(tx: FinanceTransaction) -> str:
    if tx.transaction_type == TransactionType.INCOME:
        sign = "+"
        label = "Pemasukan"
    elif tx.transaction_type == TransactionType.EXPENSE:
        sign = "-"
        label = "Pengeluaran"
    else:
        sign = ""
        label = "Transfer"

    cat_name = tx.category_name or "Lainnya"
    acc_name = tx.account_name or "—"

    lines = [
        f"*{label} Tercatat!*",
        "━━━━━━━━━━━━━━━━━━",
        f"Jumlah: *{sign}{_fmt(tx.amount)}*",
    ]
    if tx.transaction_type == TransactionType.TRANSFER:
        lines.append(f"Dari: {acc_name}")
        lines.append(f"Ke: {tx.transfer_to_account_name or '—'}")
    else:
        lines.append(f"Kategori: {cat_name}")
        lines.append(f"Rekening: {acc_name}")

    if tx.description:
        lines.append(f"Catatan: {tx.description}")

    tanggal = tx.transaction_date.strftime("%d %b %Y")
    lines += ["━━━━━━━━━━━━━━━━━━", f"Tanggal: {tanggal}"]
    return "\n".join(lines)


def format_transactions_list(
    transactions: list[FinanceTransaction], title: str = "Riwayat Transaksi"
) -> str:
    if not transactions:
        return "Belum ada transaksi yang tercatat."

    lines = [f"*{title}*", "━━━━━━━━━━━━━━━━━━"]
    for tx in transactions:
        date_str = tx.transaction_date.strftime("%d/%m")
        if tx.transaction_type == TransactionType.INCOME:
            amt = f"+{_fmt(tx.amount)}"
        elif tx.transaction_type == TransactionType.EXPENSE:
            amt = f"-{_fmt(tx.amount)}"
        else:
            amt = f"{_fmt(tx.amount)}"

        desc = tx.description or tx.category_name or "—"
        if len(desc) > 22:
            desc = desc[:20] + "…"
        lines.append(f"• `{date_str}` {desc} — *{amt}*")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"_Total: {len(transactions)} transaksi_")
    return "\n".join(lines)


def format_monthly_report(summary: MonthlySummary) -> str:
    month_name = calendar.month_name[summary.month]
    net_label = (
        f"Surplus: {_fmt(summary.net)}"
        if summary.net >= 0
        else f"Defisit: {_fmt(abs(summary.net))}"
    )

    lines = [
        f"*Laporan {month_name} {summary.year}*",
        "━━━━━━━━━━━━━━━━━━",
        f"Pemasukan: *{_fmt(summary.total_income)}*",
        f"Pengeluaran: *{_fmt(summary.total_expense)}*",
        "━━━━━━━━━━━━━━━━━━",
        f"*{net_label}*",
    ]

    if summary.top_expense_categories:
        lines += ["", "*Top Pengeluaran:*"]
        for i, cat in enumerate(summary.top_expense_categories, 1):
            lines.append(
                f"  {i}. {cat.category_name}: {_fmt(cat.total)} "
                f"({cat.transaction_count}x)"
            )

    return "\n".join(lines)


def format_accounts_list(accounts: list[FinanceAccount]) -> str:
    if not accounts:
        return "Belum ada rekening. Gunakan `!finance rekening baru <nama>` untuk membuat."

    lines = ["*Daftar Rekening*", "━━━━━━━━━━━━━━━━━━"]
    for acc in accounts:
        lines.append(f"• *{acc.name}* — {_fmt(acc.balance)}")
    return "\n".join(lines)


MONTH_NAMES_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]


def format_budget_progress(progress: BudgetProgress) -> str:
    budget = progress.budget
    cat_name = budget.category_name or "Kategori"
    month_name = (
        MONTH_NAMES_ID[budget.month]
        if 1 <= budget.month <= 12
        else str(budget.month)
    )

    status_str = progress.status.capitalize()

    lines = [
        f"*Budget {cat_name} ({month_name} {budget.year})*",
        "━━━━━━━━━━━━━━━━━━",
        f"Anggaran: *{_fmt(budget.amount)}*",
        f"Terpakai: *{_fmt(progress.spent)}*",
        f"Sisa: *{_fmt(progress.remaining)}*",
        f"Progress: *{int(progress.percentage)}%* ({status_str})",
    ]
    return "\n".join(lines)


def format_budget_list(
    budgets: list[BudgetProgress], month: int, year: int
) -> str:
    month_name = MONTH_NAMES_ID[month] if 1 <= month <= 12 else str(month)
    if not budgets:
        return f"Belum ada budget yang diatur untuk {month_name} {year}."

    lines = [f"*Budget {month_name} {year}*", "━━━━━━━━━━━━━━━━━━"]
    for p in budgets:
        b = p.budget
        name = b.category_name or "Kategori"
        lines.append(f"• *{name}*")
        lines.append(
            f"  {_fmt(p.spent)} / {_fmt(b.amount)} — *{int(p.percentage)}%* ({p.status})"
        )
        lines.append("")

    # Strip trailing blank line if any
    if lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_finance_error(exc: Exception) -> str:
    return str(exc)


def _account_icon(account_type: str) -> str:
    return ""
