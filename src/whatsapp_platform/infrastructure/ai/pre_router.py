"""Pendeteksi sapaan singkat (seperti 'halo' atau 'terima kasih').

Memungkinkan AI merespon cepat tanpa perlu mencari riwayat pesan.
"""

from __future__ import annotations

import re

_SIMPLE_CHAT_PATTERNS: set[str] = {
    "hallo", "halo", "hai", "hi", "hello", "p", "ping",
    "makasih", "terima kasih", "thanks", "thx", "tengkyu", "maturnuwun",
    "pagi", "selamat pagi", "siang", "selamat siang", "sore", "selamat sore", "malam", "selamat malam",
    "ok", "okay", "oke", "okey", "siap", "siap bos", "mantap", "sip", "jos",
    "tes", "test", "testing",
}

_ROLE_QUESTIONS: tuple[str, ...] = (
    "siapa kamu", "siapa anda", "siapa nara", "kamu siapa", "anda siapa",
    "siapa ini", "siapa namamu", "siapa nama kamu", "bot apa ini",
)

def is_simple_chat(text: str, has_finance_kw: bool = False, has_network_kw: bool = False) -> bool:
    """Mengecek apakah pesan tergolong sapaan/percakapan singkat biasa."""
    if not text:
        return True

    if has_finance_kw or has_network_kw:
        return False

    cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
    words = cleaned.split()

    if not words:
        return True

    # Check exact match in greetings set
    if cleaned in _SIMPLE_CHAT_PATTERNS:
        return True

    # Check role questions ("kamu siapa?", "siapa namamu?")
    if any(rq in cleaned for rq in _ROLE_QUESTIONS):
        return True

    # Single-word greeting matches
    if len(words) == 1 and words[0] in _SIMPLE_CHAT_PATTERNS:
        return True

    # Two-word simple greeting (e.g. "halo nara", "makasih ya", "hai bot")
    if len(words) <= 2 and words[0] in _SIMPLE_CHAT_PATTERNS and words[1] in {"nara", "bot", "min", "kak", "gan", "bro", "ya", "bos", "bang"}:
        return True

    return False
