"""Unit tests for phone_extractor module."""

from whatsapp_platform.features.customer_lookup.phone_extractor import (
    extract_phone_cores,
    normalize_phone,
)


def test_normalize_phone_valid_prefixes() -> None:
    assert normalize_phone("+628123456789") == "8123456789"
    assert normalize_phone("628123456789") == "8123456789"
    assert normalize_phone("08123456789") == "8123456789"


def test_normalize_phone_boundary_lengths() -> None:
    # 8-digit core
    assert normalize_phone("081234567") == "81234567"
    # 13-digit core
    assert normalize_phone("08123456789012") == "8123456789012"
    # Too short (<8 core digits)
    assert normalize_phone("0812345") is None
    # Too long (>13 core digits)
    assert normalize_phone("081234567890123") is None


def test_normalize_phone_invalid_start_digits() -> None:
    # Starts with 0 after prefix stripping -> invalid
    assert normalize_phone("00812345678") is None
    # Starts with 1 -> invalid
    assert normalize_phone("01812345678") is None
    # Starts with 9 -> invalid
    assert normalize_phone("09812345678") is None


def test_extract_phone_cores_text_cases() -> None:
    # Text with >5 phone numbers -> capped at 5
    text_many = (
        "Cek nomor 08123456781, 08123456782, 08123456783, "
        "08123456784, 08123456785, 08123456786, 08123456787"
    )
    cores = extract_phone_cores(text_many)
    assert len(cores) == 5
    assert cores == [
        "8123456781",
        "8123456782",
        "8123456783",
        "8123456784",
        "8123456785",
    ]

    # Text without phone numbers
    assert extract_phone_cores("Halo, ini pesan biasa tanpa nomor hp.") == []

    # Number embedded in text (e.g. "hub08123456789y")
    embedded = "Bisa hub08123456789y sekarang juga"
    assert extract_phone_cores(embedded) == ["8123456789"]

    # Deduplication check
    dups = "Nomor 08123456789 dan +628123456789 sama"
    assert extract_phone_cores(dups) == ["8123456789"]


def test_extract_phone_cores_formatted_numbers() -> None:
    assert extract_phone_cores("0896-1234-5678") == ["89612345678"]
    assert extract_phone_cores("0896 1234 5678") == ["89612345678"]
    assert extract_phone_cores("+62 896 1234 5678") == ["89612345678"]
    assert extract_phone_cores("+62-896-1234-5678") == ["89612345678"]
    assert extract_phone_cores("0896.1234.5678") == ["89612345678"]
    assert extract_phone_cores("Tolong cekkan +62 895-3322-1100 dan 0812 3456 7890 ya") == [
        "89533221100",
        "81234567890",
    ]
    assert extract_phone_cores("Tanggal 2026-05-10 dan 10-05-2026") == []

