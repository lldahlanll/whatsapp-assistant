"""Test routing dan pemilihan tool untuk variasi penambahan saldo."""

import pytest

from whatsapp_platform.infrastructure.ai.constants import classify_intent
from whatsapp_platform.infrastructure.ai.tool_policy import select_tools


def test_classify_intent_tambah_saldo() -> None:
    """Pastikan pesan bertema tambah saldo dan top up terdeteksi sebagai finance."""
    assert classify_intent("tambah saldo kas 100rb") == "finance"
    assert classify_intent("tambahkan saldo BCA 500rb") == "finance"
    assert classify_intent("top up gopay 50rb") == "finance"
    assert classify_intent("isi saldo ShopeePay 100rb") == "finance"
    assert classify_intent("setor tunai 1jt ke rekening mandiri") == "finance"
    assert classify_intent("deposit 200rb") == "finance"


def test_select_tools_tambah_saldo_includes_add_income() -> None:
    """Pastikan variasi tambah saldo dan top up menyertakan tool finance_add_income."""
    queries = [
        "tambah saldo kas 100rb",
        "tambahkan saldo BCA 500rb",
        "top up gopay 50rb",
        "topup ovo 25000",
        "isi saldo 100rb",
        "tambah uang 50rb",
        "setor tunai 200rb",
    ]

    for q in queries:
        tools = select_tools("finance", q) or []
        tool_names = [t.name for t in tools]
        assert "finance_add_income" in tool_names, f"finance_add_income harus ada untuk query '{q}', didapat: {tool_names}"


def test_select_tools_pure_balance_query_remains_balance_only() -> None:
    """Pastikan query murni cek saldo hanya memilih finance_get_balance."""
    balance_queries = [
        "berapa saldo saya sekarang?",
        "cek saldo kas",
        "sisa saldo bca",
        "berapa sisa uang saya",
    ]

    for q in balance_queries:
        tools = select_tools("finance", q) or []
        tool_names = [t.name for t in tools]
        assert tool_names == ["finance_get_balance"], f"Hanya boleh finance_get_balance untuk '{q}', didapat: {tool_names}"


def test_select_tools_create_account_precedence() -> None:
    """Pastikan pembuatan rekening baru tetap ke finance_create_account."""
    tools = select_tools("finance", "buat rekening BCA dengan saldo awal 5 juta") or []
    tool_names = [t.name for t in tools]
    assert "finance_create_account" in tool_names
    assert "finance_add_income" not in tool_names


def test_classify_intent_update_and_history() -> None:
    """Pastikan query update nominal, revisi harga, dan cek riwayat terdeteksi sebagai finance."""
    assert classify_intent("ubah harga paket data 3 jadi 50rb") == "finance"
    assert classify_intent("koreksi paket data jadi 50rb") == "finance"
    assert classify_intent("revisi harga") == "finance"
    assert classify_intent("cek riwayat") == "finance"
    assert classify_intent("ubah paket data jadi 50rb") == "finance"
    assert classify_intent("hapus transaksi kopi tadi") == "finance"


def test_select_tools_update_and_history() -> None:
    """Pastikan tool yang dipilih untuk revisi transaksi menyertakan update dan detail tools."""
    tools = select_tools("finance", "ubah harga paket data 3 jadi 50rb") or []
    tool_names = [t.name for t in tools]
    assert "finance_get_transaction_detail" in tool_names
    assert "finance_update_transaction" in tool_names

    history_tools = select_tools("finance", "cek riwayat") or []
    history_names = [t.name for t in history_tools]
    assert "finance_get_transactions" in history_names

