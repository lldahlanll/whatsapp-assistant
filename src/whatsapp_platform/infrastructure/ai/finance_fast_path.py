"""Finance Structured Action & Fast-Path Confirmation Generator.

Validates deterministic finance mutations (add expense, add income, transfer)
and formats local confirmation responses, avoiding an unnecessary second LLM call.
"""

from __future__ import annotations

import json

MUTATION_TOOLS: set[str] = {
    "finance_add_expense",
    "finance_add_income",
    "finance_transfer",
}


def try_finance_mutation_fast_path(tool_name: str, raw_tool_result: str) -> str | None:
    """Attempt fast-path confirmation template generation for successful mutations.

    Args:
        tool_name: Name of tool executed.
        raw_tool_result: Output JSON string from tool executor.

    Returns:
        Formatted WhatsApp text confirmation if successful, or None to fall back to LLM Call 2.
    """
    if tool_name not in MUTATION_TOOLS or not raw_tool_result:
        return None

    try:
        data = json.loads(raw_tool_result)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Check if transaction execution succeeded
    status = str(data.get("status", "")).lower()
    if status not in ("success", "ok"):
        return None

    # Check if error or required parameters message exists
    if data.get("error") or data.get("code") in ("ACCOUNT_REQUIRED", "ACCOUNT_NOT_FOUND"):
        return None

    # Extract transaction fields
    tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data

    amount = tx.get("amount") or data.get("amount")
    if amount is None:
        return None

    formatted_amount = f"Rp {int(amount):,}".replace(",", ".")
    account = tx.get("account_name") or data.get("account_name") or "Kas"
    category = tx.get("category_name") or data.get("category_name") or "-"
    desc = tx.get("description") or data.get("description") or "-"
    new_balance = data.get("new_balance") or data.get("balance")

    balance_str = f"\n• Saldo Terkini: Rp {int(new_balance):,}".replace(",", ".") if new_balance is not None else ""

    date = tx.get("date") or data.get("date")
    date_line = f"• Tanggal: {date}\n" if date else ""

    if tool_name == "finance_add_expense":
        return (
            f"✅ *Pengeluaran Dicatat*\n\n"
            f"• Jumlah: {formatted_amount}\n"
            f"{date_line}"
            f"• Kategori: {category}\n"
            f"• Rekening: {account}\n"
            f"• Catatan: {desc}"
            f"{balance_str}"
        )

    if tool_name == "finance_add_income":
        return (
            f"💰 *Pemasukan Dicatat*\n\n"
            f"• Jumlah: {formatted_amount}\n"
            f"{date_line}"
            f"• Kategori: {category}\n"
            f"• Rekening: {account}\n"
            f"• Catatan: {desc}"
            f"{balance_str}"
        )

    if tool_name == "finance_transfer":
        from_acc = tx.get("from_account_name") or data.get("from_account_name") or "-"
        to_acc = tx.get("to_account_name") or data.get("to_account_name") or "-"
        return (
            f"🔄 *Transfer Berhasil*\n\n"
            f"• Jumlah: {formatted_amount}\n"
            f"{date_line}"
            f"• Dari Rekening: {from_acc}\n"
            f"• Ke Rekening: {to_acc}\n"
            f"• Catatan: {desc}"
            f"{balance_str}"
        )

    return None
