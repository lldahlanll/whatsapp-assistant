"""Pengaman: tolak klaim sukses finance dari LLM yang tidak didukung pemanggilan tool.

Jika tidak ada tool finance yang dijalankan, balasan seperti "Ditambahkan: Rp220.000"
adalah karangan LLM dan data tidak tersimpan. Balasan itu diganti peringatan jujur.
"""

import re

from whatsapp_platform.infrastructure.ai.constants import BUDGET_TERMS, FINANCE_KEYWORDS

_SUCCESS_CLAIM = re.compile(
    r"\b(?:ditambahkan|berhasil|dicatat|tercatat|tersimpan|disimpan|diatur|dihapus|dibuat|diperbarui|ditransfer)\b",
    re.IGNORECASE,
)

UNBACKED_CLAIM_REPLY = (
    "Maaf, permintaan ini belum diproses dan tidak ada data yang tersimpan. "
    "Coba ulangi dengan lebih jelas, atau pakai perintah langsung, "
    "contoh: `!finance budget transportasi 220rb`."
)


def is_unbacked_finance_claim(user_text: str | None, reply: str | None) -> bool:
    """True bila pesan user bernuansa finance dan balasan mengklaim sukses tanpa tool dijalankan."""
    if not user_text or not reply:
        return False
    lower = user_text.lower()
    if not any(k in lower for k in FINANCE_KEYWORDS) and not any(k in lower for k in BUDGET_TERMS):
        return False
    return bool(_SUCCESS_CLAIM.search(reply))

