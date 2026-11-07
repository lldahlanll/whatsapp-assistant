"""Finance amount & category parser for natural language input.

Supported patterns:
  "50rb makan siang"     → 50_000, Makanan & Minuman, makan siang
  "5jt gaji bulan ini"   → 5_000_000, Gaji, gaji bulan ini
  "150k bensin"          → 150_000, Transport, bensin
  "2.5jt" / "2,5jt"      → 2_500_000
  "500000 listrik"       → 500_000, Tagihan
  "Rp 1.500.000"         → 1_500_000
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_MULTIPLIERS: dict[str, int] = {
    "jt": 1_000_000,
    "juta": 1_000_000,
    "rb": 1_000,
    "ribu": 1_000,
    "k": 1_000,
}

# Angka + satuan, mis. "2.5jt", "50 rb", "150k".
_UNIT_AMOUNT_RE = re.compile(r"(?<!\d)(\d[\d.,]*)\s*(jt|juta|rb|ribu|k)\b", re.IGNORECASE)
# Angka polos minimal 2 karakter, mis. "500000", "1.500.000".
_PLAIN_AMOUNT_RE = re.compile(r"(?<!\d)\d[\d.,]+")
# Prefix mata uang yang ikut dibuang dari deskripsi.
_CURRENCY_PREFIX_RE = re.compile(r"\brp\.?\s*$", re.IGNORECASE)


def _to_decimal(num_str: str) -> Decimal | None:
    """Konversi angka dengan pemisah ribuan/desimal gaya Indonesia atau Inggris.

    Aturan: pemisah terakhir dianggap desimal jika jumlah digit sesudahnya
    bukan 3 dan pemisah itu hanya muncul sekali (atau angka memakai titik dan
    koma sekaligus). Selain itu semua pemisah dianggap pemisah ribuan.
        "2.5" → 2.5, "1,25" → 1.25, "1.500" → 1500, "1.500.000" → 1500000,
        "1.500.000,50" → 1500000.50, "1,500,000.50" → 1500000.50
    """
    num_str = num_str.strip(".,")
    if not num_str:
        return None

    last_sep = max(num_str.rfind("."), num_str.rfind(","))
    if last_sep == -1:
        normalized = num_str
    else:
        sep = num_str[last_sep]
        tail = num_str[last_sep + 1 :]
        mixed = "." in num_str and "," in num_str
        if len(tail) != 3 and (mixed or num_str.count(sep) == 1):
            int_part = re.sub(r"[.,]", "", num_str[:last_sep])
            normalized = f"{int_part}.{tail}"
        else:
            normalized = re.sub(r"[.,]", "", num_str)

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _find_amount(text: str) -> tuple[re.Match[str], Decimal] | None:
    m = _UNIT_AMOUNT_RE.search(text)
    if m:
        base = _to_decimal(m.group(1))
        if base is None:
            return None
        return m, base * _MULTIPLIERS[m.group(2).lower()]

    m = _PLAIN_AMOUNT_RE.search(text)
    if not m:
        return None
    amount = _to_decimal(m.group(0))
    return (m, amount) if amount is not None else None


def parse_amount_from_text(text: str) -> Decimal | None:
    """Parse a natural language amount string into Decimal IDR.

    Examples:
        "50rb"      → 50_000
        "5jt"       → 5_000_000
        "150k"      → 150_000
        "500000"    → 500_000
        "1.5jt"     → 1_500_000
    """
    found = _find_amount(text.strip())
    if not found:
        return None
    amount = found[1]
    if amount == amount.to_integral_value():
        return amount.quantize(Decimal("1"))
    return amount.quantize(Decimal("0.01"))


def parse_description_without_amount(text: str) -> str:
    """Strip the numeric amount token (and any 'Rp' prefix) from text to get the description."""
    text = text.strip()
    found = _find_amount(text)
    if not found:
        return text
    m = found[0]
    before = _CURRENCY_PREFIX_RE.sub("", text[: m.start()])
    cleaned = re.sub(r"\s+", " ", f"{before} {text[m.end():]}").strip()
    return cleaned or text


def guess_category_from_text(
    text: str,
    keyword_map: dict[str, str],
) -> str | None:
    text_lower = text.lower()
    for keyword, category in keyword_map.items():
        if keyword in text_lower:
            return category
    return None
