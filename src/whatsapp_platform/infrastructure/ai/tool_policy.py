"""Memilih alat bantu (tools) yang relevan saja untuk dikirim ke AI berdasarkan isi pesan pengguna."""

from __future__ import annotations

from typing import TYPE_CHECKING

from whatsapp_platform.infrastructure.finance.tool_schema import FINANCE_TOOLS
from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS, ToolDefinition

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.ai.constants import IntentType


# Pemetaan alat bantu berdasarkan nama untuk pencarian cepat
_FINANCE_TOOL_MAP: dict[str, ToolDefinition] = {t.name: t for t in FINANCE_TOOLS}
_MIKROTIK_TOOL_MAP: dict[str, ToolDefinition] = {t.name: t for t in MIKROTIK_TOOLS}


def select_tools(intent: IntentType, text: str) -> list[ToolDefinition] | None:
    """Mengembalikan daftar alat bantu yang sesuai dengan topik pesan."""
    if intent in ("simple_chat", "chat"):
        return None

    lower = text.lower() if text else ""

    if intent == "finance":
        return _select_finance_tools(lower)

    if intent == "network":
        return _select_network_tools(lower)

    if intent == "full":
        fin_tools = _select_finance_tools(lower) or FINANCE_TOOLS
        net_tools = _select_network_tools(lower) or MIKROTIK_TOOLS
        combined: list[ToolDefinition] = []
        seen: set[str] = set()
        for t in net_tools + fin_tools:
            if t.name not in seen:
                seen.add(t.name)
                combined.append(t)
        return combined

    return None


def _select_finance_tools(lower: str) -> list[ToolDefinition]:
    """Select specific finance sub-tools based on message keywords."""
    is_budget = any(kw in lower for kw in ("budget", "anggaran"))
    is_reset = any(kw in lower for kw in (
        "reset", "hapus semua", "bersihkan semua", "mulai dari nol",
        "hapus data keuangan", "hapus semua data", "reset keuangan", "reset finance",
    ))
    is_history_query = any(kw in lower for kw in (
        "riwayat", "histori", "history", "transaksi", "terakhir",
        "list transaksi", "listkan", "tampilkan", "lihat transaksi",
    ))
    is_mutation = any(kw in lower for kw in (
        "catat", "catet", "bayar", "beli", "transfer", "pengeluaran",
        "pemasukan", "gaji", "belanja", "kirim", "keluar", "masuk",
        "top up", "topup", "top-up", "isi saldo", "tambah saldo",
        "tambahkan saldo", "tambah uang", "tambahkan uang", "isi ulang",
        "setor", "setor tunai", "deposit", "masukin", "masukkan",
    ))
    is_report = any(kw in lower for kw in ("rekap", "laporan", "summary", "bulan ini"))
    is_account_create = any(kw in lower for kw in (
        "buat rekening", "bikin rekening", "tambah rekening", "tambahkan rekening",
        "rekening baru", "buka rekening", "buat akun", "bikin akun", "tambah akun",
        "tambahkan akun", "akun baru", "buka akun", "bikin dompet", "tambah dompet",
    ))
    is_modify_or_delete = any(kw in lower for kw in (
        "hapus", "ubah", "koreksi", "edit", "salah", "batalkan", "cancel", "ganti",
    ))
    is_account_query = any(kw in lower for kw in (
        "daftar rekening", "daftar akun", "akun apa", "rekening apa",
        "dompet apa", "akun saya", "rekening saya", "punya rekening",
        "list rekening", "lihat rekening", "cek rekening",
    ))
    is_balance_query = any(kw in lower for kw in (
        "saldo", "berapa uang", "berapa duit", "berapa sisa", "cek saldo",
    ))
    is_confirmation = any(kw == lower.strip() or kw in lower.split() for kw in (
        "ya", "iya", "y", "yes", "oke", "ok", "lanjut", "lanjutkan",
        "yakin", "benar", "betul", "setuju", "hapus"
    ))
    is_kategori_query = any(kw in lower for kw in ("kategori", "kategori apa"))

    names: list[str] = []

    if is_confirmation:
        names = [
            "finance_delete_account",
            "finance_delete_transaction",
            "finance_reset_data",
            "finance_get_accounts",
            "finance_get_balance",
        ]
    elif is_reset:
        names = ["finance_reset_data"]
    elif is_account_create:
        names = ["finance_create_account", "finance_get_accounts", "finance_get_balance"]
    elif is_budget:
        names = [
            "finance_create_budget",
            "finance_get_budget",
            "finance_list_budgets",
            "finance_delete_budget",
            "finance_get_categories",
        ]
    elif is_modify_or_delete:
        # Tentukan lebih spesifik: hapus rekening vs hapus transaksi vs hapus budget
        if any(kw in lower for kw in ("rekening", "akun", "dompet", "kas")):
            names = ["finance_delete_account", "finance_get_accounts"]
        elif any(kw in lower for kw in ("budget", "anggaran")):
            names = ["finance_delete_budget", "finance_list_budgets"]
        else:
            names = [
                "finance_get_transaction_detail",
                "finance_update_transaction",
                "finance_delete_transaction",
                "finance_get_transactions",
            ]
    elif is_history_query:
        names = ["finance_get_transactions"]
    elif is_account_query:
        names = ["finance_get_accounts", "finance_get_balance"]
    elif is_kategori_query:
        names = ["finance_get_categories"]
    elif is_mutation:
        names = [
            "finance_add_expense",
            "finance_add_income",
            "finance_transfer",
            "finance_get_balance",
            "finance_get_accounts",
            "finance_get_categories",
        ]
    elif is_report:
        names = [
            "finance_get_monthly_report",
            "finance_get_expense_summary",
            "finance_get_transactions",
            "finance_get_balance",
            "finance_list_budgets",
        ]
    elif is_balance_query:
        names = ["finance_get_balance"]
    else:
        return FINANCE_TOOLS

    selected = [_FINANCE_TOOL_MAP[n] for n in names if n in _FINANCE_TOOL_MAP]
    return selected if selected else FINANCE_TOOLS


def _select_network_tools(lower: str) -> list[ToolDefinition]:
    """Select specific MikroTik sub-tools based on message keywords."""
    is_health = any(kw in lower for kw in ("cpu", "health", "suhu", "temp", "ram", "memory", "uptime", "kondisi", "status", "sehat"))
    is_traffic = any(kw in lower for kw in ("traffic", "interface", "bandwidth", "speed", "port", "pemakaian", "penggunaan"))
    is_dhcp = any(kw in lower for kw in ("client", "perangkat", "dhcp", "lease", "terhubung", "koneksi", "siapa aja", "hp", "laptop"))
    is_security = any(kw in lower for kw in ("firewall", "keamanan", "security", "block", "drop", "hack"))
    is_routes = any(kw in lower for kw in ("route", "routing", "ping", "gateway", "indihome", "biznet", "myrepublic"))
    is_logs = any(kw in lower for kw in ("log", "error", "gangguan", "lambat", "lemot", "putus", "masalah"))

    names: list[str] = []

    if is_health and not (is_traffic or is_dhcp or is_logs):
        names = ["mikrotik_get_health"]
    elif is_traffic and not is_logs:
        names = ["mikrotik_get_traffic", "mikrotik_get_health"]
    elif is_dhcp:
        names = ["mikrotik_get_dhcp_leases"]
    elif is_security:
        names = ["mikrotik_audit_security", "mikrotik_get_firewall"]
    elif is_routes:
        names = ["mikrotik_get_routes", "mikrotik_get_logs"]
    elif is_logs:
        names = ["mikrotik_get_logs", "mikrotik_get_health", "mikrotik_get_traffic"]
    else:
        return MIKROTIK_TOOLS

    selected = [_MIKROTIK_TOOL_MAP[n] for n in names if n in _MIKROTIK_TOOL_MAP]
    return selected if selected else MIKROTIK_TOOLS
