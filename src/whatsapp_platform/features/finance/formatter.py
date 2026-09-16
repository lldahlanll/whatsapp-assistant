"""Finance output formatter — menghasilkan teks siap kirim ke WhatsApp."""

from __future__ import annotations

import calendar
from datetime import date, datetime
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
    if not accounts:
        return (
            "*Saldo Rekening*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Belum ada rekening/dompet terdaftar.\n\n"
            "Gunakan perintah berikut untuk membuat rekening:\n"
            "  `!finance rekening baru <nama> [tipe] [saldo_awal]`\n"
            "Contoh: `!finance rekening baru BCA bank 1jt`"
        )

    total: Decimal = data.get("total", Decimal("0"))

    available_accs = [
        a
        for a in accounts
        if a.get("classification") == "available"
        or (a.get("type", "bank").lower() in ("cash", "bank", "ewallet", "savings"))
    ]
    investment_accs = [
        a
        for a in accounts
        if a.get("classification") == "investment"
        or (a.get("type", "").lower() in ("deposit", "investment"))
    ]

    lines = ["*Saldo Rekening*", "━━━━━━━━━━━━━━━━━━"]
    if investment_accs and available_accs:
        lines.append("*Saldo Tersedia:*")
        for acc in available_accs:
            lines.append(f"• *{acc['name']}*: {_fmt(acc['balance'])}")

        lines.append("")
        lines.append("*Investasi:*")
        for acc in investment_accs:
            lines.append(f"• *{acc['name']}*: {_fmt(acc['balance'])}")

        lines += ["━━━━━━━━━━━━━━━━━━", f"*Total Aset: {_fmt(total)}*"]
    elif investment_accs and not available_accs:
        lines.append("*Investasi:*")
        for acc in investment_accs:
            lines.append(f"• *{acc['name']}*: {_fmt(acc['balance'])}")
        lines += ["━━━━━━━━━━━━━━━━━━", f"*Total Aset: {_fmt(total)}*"]
    else:
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


MONTH_ABBR_ID = [
    "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des"
]


def format_tx_date(val: datetime | date | str | None, include_year: bool = False) -> str:
    """Format tanggal ke format Indonesia ringkas, misal '14 Sep'."""
    if not val:
        return ""
    if hasattr(val, "day") and hasattr(val, "month"):
        day = val.day
        month = val.month
        mon_str = MONTH_ABBR_ID[month] if 1 <= month <= 12 else str(month)
        if include_year and hasattr(val, "year"):
            return f"{day} {mon_str} {val.year}"
        return f"{day} {mon_str}"
    if isinstance(val, str):
        parts = val.split("T")[0].split("-")
        if len(parts) == 3:
            try:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                mon_str = MONTH_ABBR_ID[month] if 1 <= month <= 12 else str(month)
                if include_year:
                    return f"{day} {mon_str} {year}"
                return f"{day} {mon_str}"
            except ValueError:
                pass
        return val
    return str(val)


def format_transactions_list(
    transactions: list[FinanceTransaction], title: str = "Riwayat Transaksi"
) -> str:
    if not transactions:
        return "Belum ada transaksi yang tercatat."

    clean_title = title.strip("*").upper()
    header = f"📜 *{clean_title}*"
    items = []
    for tx in transactions:
        amt_num = _fmt(tx.amount)
        if tx.transaction_type == TransactionType.INCOME:
            icon = "🟢"
            amt_str = f"{icon} *+{amt_num}*"
        elif tx.transaction_type == TransactionType.EXPENSE:
            icon = "🔴"
            amt_str = f"{icon} *-{amt_num}*"
        else:
            icon = "🔵"
            amt_str = f"{icon} *{amt_num}*"

        desc = tx.description or tx.category_name or "—"
        date_str = format_tx_date(tx.transaction_date)
        acc_str = f" ({tx.account_name})" if tx.account_name else ""
        detail = f"{desc}{acc_str}"

        items.append(f"• {date_str} | {amt_str} | {detail}")

    return f"{header}\n\n" + "\n".join(items)


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

    available_accs = [a for a in accounts if a.is_available_balance]
    investment_accs = [a for a in accounts if a.is_investment]

    lines = ["*Daftar Rekening*", "━━━━━━━━━━━━━━━━━━"]
    if investment_accs and available_accs:
        lines.append("*Saldo Tersedia:*")
        for acc in available_accs:
            lines.append(f"• *{acc.name}* ({acc.account_type.value}) — {_fmt(acc.balance)}")
        lines.append("")
        lines.append("*Investasi:*")
        for acc in investment_accs:
            lines.append(f"• *{acc.name}* ({acc.account_type.value}) — {_fmt(acc.balance)}")
    elif investment_accs and not available_accs:
        lines.append("*Investasi:*")
        for acc in investment_accs:
            lines.append(f"• *{acc.name}* ({acc.account_type.value}) — {_fmt(acc.balance)}")
    else:
        for acc in accounts:
            lines.append(f"• *{acc.name}* ({acc.account_type.value}) — {_fmt(acc.balance)}")
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
