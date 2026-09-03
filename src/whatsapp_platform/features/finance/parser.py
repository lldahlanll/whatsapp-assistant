"""Finance amount & category parser for natural language input.

Supported patterns:
  "50rb makan siang"     → 50_000, Makanan & Minuman, makan siang
  "5jt gaji bulan ini"   → 5_000_000, Gaji, gaji bulan ini
  "150k bensin"          → 150_000, Transport, bensin
  "2.5jt"                → 2_500_000
  "500000 listrik"       → 500_000, Tagihan
"""

from __future__ import annotations

import re
from decimal import Decimal

_MULTIPLIERS: dict[str, int] = {
    "jt": 1_000_000,
    "juta": 1_000_000,
    "rb": 1_000,
    "ribu": 1_000,
    "k": 1_000,
}


def parse_amount_from_text(text: str) -> Decimal | None:
    """Parse a natural language amount string into Decimal IDR.

    Examples:
        "50rb"      → 50_000
        "5jt"       → 5_000_000
        "150k"      → 150_000
        "500000"    → 500_000
        "1.5jt"     → 1_500_000
    """
    text = text.strip()
    m = re.search(
        r"(\d[\d.,]*)(\s*)(jt|juta|rb|ribu|k)\b",
        text,
        re.IGNORECASE,
    )
    if not m:
        # No unit — try plain integer
        m2 = re.search(r"(\d[\d.,]+)", text)
        if not m2:
            return None
        num_str = m2.group(1).replace(".", "").replace(",", "")
        try:
            return Decimal(num_str)
        except Exception:
            return None

    num_str = m.group(1)
    unit = (m.group(3) or "").lower().strip()

    num_str = num_str.replace(".", "").replace(",", "")
    try:
        base = Decimal(num_str)
    except Exception:
        return None

    multiplier = _MULTIPLIERS.get(unit, 1)
    return base * multiplier


def parse_description_without_amount(text: str) -> str:
    """Strip the numeric amount token from text to get the description."""
    cleaned = re.sub(
        r"\d[\d.,]*\s*(jt|juta|rb|ribu|k|m|M)?\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or text.strip()


def guess_category_from_text(
    text: str,
    keyword_map: dict[str, str],
) -> str | None:
    text_lower = text.lower()
    for keyword, category in keyword_map.items():
        if keyword in text_lower:
            return category
    return None
