"""Finance Structured Action & Fast-Path Confirmation Generator.

Validates deterministic finance mutations (add expense, add income, transfer)
and formats local confirmation responses, avoiding an unnecessary second LLM call.

Also handles all read-only query tools and other mutation results so that
the agentic loop returns after exactly 1 LLM call in most cases.
"""

from __future__ import annotations

import json

from whatsapp_platform.features.finance.formatter import format_tx_date

# ── Mutation tools (original fast-path) ───────────────────────────────────────

MUTATION_TOOLS: set[str] = {
    "finance_add_expense",
    "finance_add_income",
    "finance_transfer",
}

GROUP_PRIVATE_TOOLS: set[str] = {
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


def is_group_blocked_tool(tool_name: str) -> bool:
    """Return True if tool should be blocked in a group chat."""
    return tool_name in GROUP_PRIVATE_TOOLS

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

    account = tx.get("account_name") or data.get("account_name") or "—"
    category = (
        tx.get("category_name")
        or tx.get("category")
        or data.get("category_name")
        or data.get("category")
        or "-"
    )
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

    account = tx.get("account_name") or data.get("account_name") or "—"
    category = (
        tx.get("category_name")
        or tx.get("category")
        or data.get("category_name")
        or data.get("category")
        or "-"
    )
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

    header = "📜 *RIWAYAT TRANSAKSI*"
    items = []
    for tx in transactions:
        tx_type = str(tx.get("type", "")).lower()
        amt_val = abs(float(tx.get("amount", 0)))
        amt_num = _fmt_rp(amt_val)
        if tx_type == "income":
            icon = "🟢"
            amt_str = f"{icon} *+{amt_num}*"
        elif tx_type == "expense":
            icon = "🔴"
            amt_str = f"{icon} *-{amt_num}*"
        else:
            icon = "🔵"
            amt_str = f"{icon} *{amt_num}*"

        desc = tx.get("description") or tx.get("category") or tx.get("type", "") or "—"
        date_str = format_tx_date(tx.get("date"))
        acc = tx.get("account") or ""
        acc_str = f" ({acc})" if acc else ""
        detail = f"{desc}{acc_str}"

        items.append(f"• {date_str} | {amt_str} | {detail}")

    return f"{header}\n\n" + "\n".join(items)


@_handler("finance_get_balance")
def _fast_get_balance(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        return None

    accounts = data.get("accounts", [])
    if not accounts:
        return "Belum ada rekening aktif. Silakan buat rekening terlebih dahulu (contoh: 'buat rekening BCA saldo awal 1jt')."

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

    total = sum(float(acc.get("balance", 0)) for acc in accounts)

    if investment_accs and available_accs:
        lines = ["*Saldo Rekening*\n", "*Saldo Tersedia:*"]
        for acc in available_accs:
            lines.append(f"• *{acc.get('name')}* — {_fmt_rp(acc.get('balance', 0))}")

        lines.append("\n*Investasi:*")
        for acc in investment_accs:
            lines.append(f"• *{acc.get('name')}* — {_fmt_rp(acc.get('balance', 0))}")

        lines.append(f"\n*Total Aset: {_fmt_rp(total)}*")
        return "\n".join(lines)
    elif investment_accs and not available_accs:
        lines = ["*Saldo Rekening*\n", "*Investasi:*"]
        for acc in investment_accs:
            lines.append(f"• *{acc.get('name')}* — {_fmt_rp(acc.get('balance', 0))}")

        lines.append(f"\n*Total Aset: {_fmt_rp(total)}*")
        return "\n".join(lines)
    else:
        lines = ["*Saldo Rekening*\n"]
        for acc in accounts:
            balance = acc.get("balance", 0)
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

    available_accs = [
        a
        for a in accounts
        if (a.get("type") or "bank").lower() in ("cash", "bank", "ewallet", "savings")
    ]
    investment_accs = [
        a
        for a in accounts
        if (a.get("type") or "").lower() in ("deposit", "investment")
    ]

    if investment_accs and available_accs:
        lines = [f"*Daftar Rekening* ({len(accounts)} rekening)\n", "*Saldo Tersedia:*"]
        for acc in available_accs:
            acc_type = (acc.get("type") or "bank").lower()
            lines.append(f"• *{acc.get('name')}* ({acc_type}) — {_fmt_rp(acc.get('balance', 0))}")
        lines.append("\n*Investasi:*")
        for acc in investment_accs:
            acc_type = (acc.get("type") or "investment").lower()
            lines.append(f"• *{acc.get('name')}* ({acc_type}) — {_fmt_rp(acc.get('balance', 0))}")
        return "\n".join(lines)

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


@_handler("finance_update_transaction")
def _fast_update_transaction(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        # Return explicit error so LLM doesn't hallucinate a success response
        error_msg = data.get("message", "")
        error_code = data.get("error_code", "")
        if error_code == "TRANSACTION_NOT_FOUND" or "tidak ditemukan" in error_msg.lower():
            return (
                "❌ *Gagal memperbarui transaksi*\n\n"
                "Transaksi tidak ditemukan. Gunakan perintah *cek riwayat* atau "
                "sebutkan kata kunci transaksi agar saya bisa mencarinya terlebih dahulu."
            )
        if error_msg:
            return f"❌ *Gagal memperbarui transaksi*\n\n{error_msg}"
        # Fallback generic error — never let LLM interpret this as success
        return "❌ *Gagal memperbarui transaksi*\n\nTerjadi kesalahan. Coba lagi atau cek riwayat transaksi terlebih dahulu."

    tx_id = data.get("transaction_id") or data.get("new_transaction_id", "")
    amount = data.get("amount") or data.get("new_amount")
    desc = data.get("description") or data.get("new_description") or "—"
    cat = data.get("category") or data.get("new_category")
    acc = data.get("account") or data.get("new_account")

    lines = [
        f"*Transaksi Berhasil Diperbarui!*\n",
    ]
    if tx_id:
        lines.append(f"• ID: `{tx_id}`")
    if amount is not None:
        lines.append(f"• Nominal Baru: {_fmt_rp(amount)}")
    if desc and desc != "—":
        lines.append(f"• Catatan: {desc}")
    if cat:
        lines.append(f"• Kategori: {cat}")
    if acc:
        lines.append(f"• Rekening: {acc}")

    return "\n".join(lines)


@_handler("finance_delete_transaction")
def _fast_delete_transaction(data: dict) -> str | None:
    status = str(data.get("status", "")).lower()
    if status != "success":
        error_msg = data.get("message", "")
        error_code = data.get("error_code", "")
        if error_code == "TRANSACTION_NOT_FOUND" or "tidak ditemukan" in error_msg.lower():
            return (
                "❌ *Gagal menghapus transaksi*\n\n"
                "Transaksi tidak ditemukan. Gunakan *cek riwayat* untuk melihat ID transaksi yang benar."
            )
        if error_msg:
            return f"❌ *Gagal menghapus transaksi*\n\n{error_msg}"
        return "❌ *Gagal menghapus transaksi*\n\nTerjadi kesalahan saat menghapus transaksi."

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


def try_finance_mutation_fast_path(
    tool_name: str,
    raw_tool_result: str,
    is_group: bool = False,
) -> str | None:
    """Attempt fast-path confirmation template generation.

    Covers both mutation tools and all read-only query tools to eliminate
    the second LLM call in the agentic tool-calling loop.

    Args:
        tool_name: Name of tool executed.
        raw_tool_result: Output JSON string from tool executor.
        is_group: Whether the execution context is a group chat.

    Returns:
        Formatted WhatsApp text confirmation if successful, or None to fall back to LLM Call 2.
    """
    if not raw_tool_result:
        return None

    try:
        data = json.loads(raw_tool_result)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    if is_group:
        if data.get("error_code") == "GROUP_PRIVATE_ONLY":
            return data.get(
                "message",
                "Data keuangan pribadi hanya dapat dilihat di chat private. Silakan hubungi saya lewat chat pribadi.",
            )
        if is_group_blocked_tool(tool_name):
            return "Data keuangan pribadi hanya dapat dilihat di chat private. Silakan hubungi saya lewat chat pribadi."

        # Strip balance info from mutation confirmations in group context
        data.pop("new_balance", None)
        data.pop("balance", None)
        if isinstance(data.get("transaction"), dict):
            data["transaction"].pop("new_balance", None)
            data["transaction"].pop("balance", None)

    handler = _FAST_PATH_HANDLERS.get(tool_name)
    if handler is None:
        return None

    try:
        return handler(data)
    except Exception:
        return None
