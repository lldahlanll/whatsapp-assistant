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


# Klaim mutasi finance yang spesifik (dipakai saat jalur tool bukan finance, mis. pesan campuran
# "ingetin bayar air besok, catat juga makan 50rb" yang dirutekan ke tool pengingat saja).
_AMOUNT = re.compile(r"(?i)(\brp\.?\s?\d|\b\d+([.,]\d+)?\s?(rb|ribu|k|jt|juta)\b|\b\d{4,}\b)")
_FINANCE_NOUN = r"(pengeluaran|pemasukan|transaksi|transfer|saldo|budget|anggaran|rekening|dompet)"
_FINANCE_VERB = r"(dicatat|tercatat|ditambahkan|tersimpan|disimpan|diatur|dihapus|diperbarui|ditransfer|berhasil)"
_FINANCE_ACTION_CLAIM = re.compile(
    rf"(?i)(\b{_FINANCE_NOUN}\b[^.\n]{{0,60}}?\b{_FINANCE_VERB}\b"
    rf"|\b{_FINANCE_VERB}\b[^.\n]{{0,30}}?\b{_FINANCE_NOUN}\b"
    r"|(\brp\.?\s?[\d.,]+|\b\d+([.,]\d+)?\s?(rb|ribu|k|jt|juta)\b)[^.\n]{0,40}?\b(dicatat|tercatat|ditambahkan|ditransfer)\b)"
)

UNBACKED_FINANCE_NOTE = (
    "⚠️ *Catatan:* transaksi/budget keuangan yang disebut di atas *belum tercatat*. "
    "Kirim ulang secara terpisah, contoh: _'catat pengeluaran makan 50rb'_."
)


def is_unbacked_finance_action_claim(user_text: str | None, reply: str | None) -> bool:
    """User menyebut nominal + kata finance, dan balasan mengklaim mutasi finance tersimpan.

    Pemanggil wajib memastikan tidak ada tool ``finance_*`` yang sukses di giliran ini.
    """
    if not user_text or not reply:
        return False
    lower = user_text.lower()
    if not _AMOUNT.search(lower):
        return False
    if not any(k in lower for k in FINANCE_KEYWORDS) and not any(k in lower for k in BUDGET_TERMS):
        return False
    return bool(_FINANCE_ACTION_CLAIM.search(reply))


# ── Pengingat ─────────────────────────────────────────────────────────────────
# Bot hanya bisa mengirim pengingat jika reminder_create benar-benar sukses. Tanpa itu,
# "Pengingat diset" / "nanti aku ingatkan" adalah janji palsu: pesan tidak akan pernah terkirim.

_REMINDER_CUE = re.compile(
    r"(?i)\b(ingat\w*|inget\w*|kabari\w*|kabarin|pengingat|reminder|remind|alarm|jadwal\w*|"
    r"\d+\s*(menit|mnt|jam)\s*lagi|(besok|nanti)\s+(pagi|siang|sore|malam|jam))\b"
)

_REMINDER_CLAIM = re.compile(
    r"(?i)("
    r"\b(pengingat|reminder|alarm|jadwal)\b[^.\n]{0,40}?"
    r"\b(diset|disetel|dipasang|dibuat|tersimpan|disimpan|diaktifkan|aktif|berhasil|sudah|siap|terpasang)\b"
    r"|\b(akan|nanti|bakal|pasti)\s+(aku|saya|ku|kami|bot)?\s*"
    r"(ingatkan|ingetin|ingatin|kabari|kabarin|beritahu|kasih tahu)\b"
    r"|\b(aku|saya)\s+(akan\s+)?(ingatkan|ingetin|ingatin|kabari|kabarin)\s+(kamu|kak|kakak|anda|lagi|nanti|\d)"
    r"|\bkuingatkan\b"
    r")"
)

UNBACKED_REMINDER_NOTE = (
    "⚠️ *Catatan:* pengingat yang disebut di atas *belum tersimpan* dan tidak akan terkirim. "
    "Kirim ulang, contoh: _'ingetin makan 5 menit lagi'_ atau `!pengingat 5m makan`."
)

UNBACKED_REMINDER_REPLY = (
    "Maaf, pengingatnya belum tersimpan, jadi tidak akan terkirim. "
    "Coba ulangi dengan jelas, contoh: _'ingetin makan 5 menit lagi'_, "
    "atau pakai perintah `!pengingat 5m makan`."
)


def is_unbacked_reminder_claim(user_text: str | None, reply: str | None) -> bool:
    """True bila user meminta pengingat/berwaktu dan balasan menjanjikan pengingat.

    Pemanggil wajib memastikan tidak ada reminder_create yang sukses di giliran ini.
    """
    if not user_text or not reply:
        return False
    return bool(_REMINDER_CUE.search(user_text) and _REMINDER_CLAIM.search(reply))
