"""Unit tests for Customer Lookup formatter module."""

from datetime import datetime

from whatsapp_platform.features.customer_lookup.formatter import (
    format_date_indonesian,
    format_reply,
    mask_phone,
)
from whatsapp_platform.infrastructure.customer_lookup.models import CustomerRecord


def test_mask_phone() -> None:
    assert mask_phone("8123456789") == "0812xxxx6789"
    assert mask_phone("08123456789") == "0812xxxx6789"
    assert mask_phone("+628123456789") == "0812xxxx6789"
    # Short number
    assert mask_phone("0812345") == "08xxxx45"
    # Empty
    assert mask_phone("") == "xxxx"


def test_format_date_indonesian() -> None:
    dt = datetime(2026, 5, 13, 10, 30)
    assert format_date_indonesian(dt) == "13 Mei 2026"

    dt2 = datetime(2025, 1, 1)
    assert format_date_indonesian(dt2) == "1 Januari 2025"


def test_format_reply_empty_records() -> None:
    reply = format_reply([], query_phone_core="8123456789")
    assert reply == "Nomor 0812xxxx6789 belum terdaftar. coba daftarkan ulang ya"


def test_format_reply_with_records() -> None:
    rec1 = CustomerRecord(
        kode_kustomer="CUST-100",
        no_hp="08123456789",
        add_user="JOKO",
        add_date=datetime(2026, 5, 13, 8, 0),
    )
    rec2 = CustomerRecord(
        kode_kustomer="CUST-099",
        no_hp="08123456789",
        add_user="JOKO",
        add_date=datetime(2026, 5, 12, 8, 0),
    )
    reply = format_reply([rec1, rec2], query_phone_core="8123456789")
    assert reply == "CUST-100"
