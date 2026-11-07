"""Tests for the natural-language amount parser (decimal and thousands separators)."""

from decimal import Decimal

import pytest

from whatsapp_platform.features.finance.parser import (
    parse_amount_from_text,
    parse_description_without_amount,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("50rb", Decimal("50000")),
        ("5jt", Decimal("5000000")),
        ("5 jt", Decimal("5000000")),
        ("150k", Decimal("150000")),
        ("500000", Decimal("500000")),
        # Desimal dengan satuan: dulu terbaca 10x lipat
        ("2.5jt", Decimal("2500000")),
        ("2,5jt", Decimal("2500000")),
        ("1.25jt", Decimal("1250000")),
        # Pemisah ribuan
        ("1.500.000", Decimal("1500000")),
        ("1,500,000", Decimal("1500000")),
        ("1.500rb", Decimal("1500000")),
        ("Rp 25.000", Decimal("25000")),
        # Ribuan + desimal campuran
        ("1.500.000,50", Decimal("1500000.50")),
        ("1,500,000.50", Decimal("1500000.50")),
        ("makan siang", None),
    ],
)
def test_parse_amount(text: str, expected: Decimal | None) -> None:
    assert parse_amount_from_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("50rb makan siang", "makan siang"),
        ("2.5jt beli hp", "beli hp"),
        ("1.500.000 listrik", "listrik"),
        # Angka lain di kalimat tidak boleh ikut terpotong
        ("beli 2 kopi 30rb", "beli 2 kopi"),
        ("bayar 3x 100rb", "bayar 3x"),
        ("Rp25.000 parkir", "parkir"),
        ("parkir Rp 5.000 mall", "parkir mall"),
    ],
)
def test_parse_description_strips_only_amount(text: str, expected: str) -> None:
    assert parse_description_without_amount(text) == expected
