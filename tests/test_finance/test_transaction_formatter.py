import json
from datetime import datetime
from decimal import Decimal

from whatsapp_platform.domain.entities.finance import FinanceTransaction, TransactionType
from whatsapp_platform.features.finance.formatter import (
    format_transactions_list,
    format_tx_date,
)
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path


def test_format_tx_date():
    assert format_tx_date("2026-09-14") == "14 Sep"
    assert format_tx_date("2026-09-13") == "13 Sep"
    assert format_tx_date("2026-09-12") == "12 Sep"
    assert format_tx_date(datetime(2026, 9, 14, 15, 30)) == "14 Sep"
    assert format_tx_date(datetime(2026, 1, 1)) == "1 Jan"
    assert format_tx_date(datetime(2026, 5, 2)) == "2 Mei"
    assert format_tx_date(datetime(2026, 8, 17)) == "17 Agu"
    assert format_tx_date(datetime(2026, 10, 28)) == "28 Okt"
    assert format_tx_date(datetime(2026, 12, 25)) == "25 Des"
    assert format_tx_date(None) == ""
    # With year
    assert format_tx_date("2026-09-14", include_year=True) == "14 Sep 2026"
    assert format_tx_date(datetime(2026, 9, 14), include_year=True) == "14 Sep 2026"


def test_format_transactions_list_user_example():
    """Verify format_transactions_list outputs the exact format requested by user."""
    transactions = [
        FinanceTransaction(
            id="tx1",
            owner_jid="user@s.whatsapp.net",
            account_id="acc1",
            account_name="Kas Tunai",
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("11000"),
            category_id="cat1",
            category_name="Makanan",
            description="Beli makan",
            transaction_date=datetime(2026, 9, 14, 10, 0),
            transfer_to_account_id=None,
            created_at=datetime(2026, 9, 14, 10, 0),
        ),
        FinanceTransaction(
            id="tx2",
            owner_jid="user@s.whatsapp.net",
            account_id="acc2",
            account_name="BCA",
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("15000"),
            category_id="cat1",
            category_name="Makanan",
            description="Makanan",
            transaction_date=datetime(2026, 9, 13, 10, 0),
            transfer_to_account_id=None,
            created_at=datetime(2026, 9, 13, 10, 0),
        ),
        FinanceTransaction(
            id="tx3",
            owner_jid="user@s.whatsapp.net",
            account_id="acc2",
            account_name="BCA",
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("101750"),
            category_id="cat2",
            category_name="Tagihan",
            description="Token Listrik",
            transaction_date=datetime(2026, 9, 13, 11, 0),
            transfer_to_account_id=None,
            created_at=datetime(2026, 9, 13, 11, 0),
        ),
        FinanceTransaction(
            id="tx4",
            owner_jid="user@s.whatsapp.net",
            account_id="acc2",
            account_name="BCA",
            transaction_type=TransactionType.INCOME,
            amount=Decimal("500000"),
            category_id="cat3",
            category_name="Pemasukan",
            description="Setor Tunai",
            transaction_date=datetime(2026, 9, 12, 13, 0),
            transfer_to_account_id=None,
            created_at=datetime(2026, 9, 12, 13, 0),
        ),
    ]

    expected = (
        "📜 *RIWAYAT TRANSAKSI*\n\n"
        "• 14 Sep | 🔴 *-Rp 11.000* | Beli makan (Kas Tunai)\n"
        "• 13 Sep | 🔴 *-Rp 15.000* | Makanan (BCA)\n"
        "• 13 Sep | 🔴 *-Rp 101.750* | Token Listrik (BCA)\n"
        "• 12 Sep | 🟢 *+Rp 500.000* | Setor Tunai (BCA)"
    )

    result = format_transactions_list(transactions)
    assert result == expected


def test_fast_path_get_transactions_user_example():
    """Verify finance_get_transactions fast path outputs the exact user layout."""
    raw_res = json.dumps({
        "status": "success",
        "count": 4,
        "transactions": [
            {
                "transaction_id": "TX01",
                "date": "2026-09-14",
                "type": "expense",
                "amount": 11000,
                "description": "Beli makan",
                "account": "Kas Tunai",
            },
            {
                "transaction_id": "TX02",
                "date": "2026-09-13",
                "type": "expense",
                "amount": 15000,
                "description": "Makanan",
                "account": "BCA",
            },
            {
                "transaction_id": "TX03",
                "date": "2026-09-13",
                "type": "expense",
                "amount": 101750,
                "description": "Token Listrik",
                "account": "BCA",
            },
            {
                "transaction_id": "TX04",
                "date": "2026-09-12",
                "type": "income",
                "amount": 500000,
                "description": "Setor Tunai",
                "account": "BCA",
            },
        ],
    })

    expected = (
        "📜 *RIWAYAT TRANSAKSI*\n\n"
        "• 14 Sep | 🔴 *-Rp 11.000* | Beli makan (Kas Tunai)\n"
        "• 13 Sep | 🔴 *-Rp 15.000* | Makanan (BCA)\n"
        "• 13 Sep | 🔴 *-Rp 101.750* | Token Listrik (BCA)\n"
        "• 12 Sep | 🟢 *+Rp 500.000* | Setor Tunai (BCA)"
    )

    result = try_finance_mutation_fast_path("finance_get_transactions", raw_res)
    assert result == expected


def test_format_transactions_empty():
    assert format_transactions_list([]) == "Belum ada transaksi yang tercatat."
    raw_res = json.dumps({"status": "success", "transactions": []})
    assert try_finance_mutation_fast_path("finance_get_transactions", raw_res) == "Belum ada transaksi yang tercatat."
