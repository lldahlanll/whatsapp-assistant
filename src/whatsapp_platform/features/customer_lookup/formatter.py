"""Formatter module for Customer Lookup responses and PII masking."""

import re
from datetime import datetime

from whatsapp_platform.infrastructure.customer_lookup.models import CustomerRecord

INDONESIAN_MONTHS = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


def mask_phone(phone: str) -> str:
    """Format phone number with PII masking (e.g. '0812xxxx6789').

    Args:
        phone: Raw or normalized phone number string.

    Returns:
        Masked phone number string.
    """
    if not phone:
        return "xxxx"

    digits = re.sub(r"\D", "", phone)
    if not digits:
        return "xxxx"

    # Standardize to 08xx display format if starting with 62 or core digit
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    elif not digits.startswith("0"):
        digits = "0" + digits

    length = len(digits)
    if length <= 8:
        head = digits[:2]
        tail = digits[-2:] if length >= 4 else ""
        return f"{head}xxxx{tail}"

    head = digits[:4]
    tail = digits[-4:]
    return f"{head}xxxx{tail}"


def format_date_indonesian(dt: datetime) -> str:
    """Format a datetime into locale-safe Indonesian date string (e.g. '13 Mei 2026')."""
    month_name = INDONESIAN_MONTHS.get(dt.month, str(dt.month))
    return f"{dt.day} {month_name} {dt.year}"


def format_reply(records: list[CustomerRecord], query_phone_core: str = "") -> str:
    if not records:
        masked_query = mask_phone(query_phone_core) if query_phone_core else "tersebut"
        return f"Nomor {masked_query} belum terdaftar. coba daftarkan ulang ya"

    # Karena query database sudah diurutkan ORDER BY AddDate DESC,
    # records[0] adalah data yang paling terbaru.
    latest_record = records[0]
    return latest_record.kode_kustomer.strip() if latest_record.kode_kustomer else ""
