# app/ai/postprocess.py
"""
Post-processing untuk LLM output.

Masalah yang di-handle:
1. <think>...</think> tag dari reasoning models (Qwen3, DeepSeek-R1, dll)
   → Strip sebelum response dikirim ke user
2. Response terlalu panjang untuk WhatsApp
   → Truncate dengan graceful cutoff
"""
import re
from typing import Optional


# ── Pattern untuk thinking tags ──────────────────────────────

# Qwen3, DeepSeek-R1 style
_THINK_TAG_PATTERN = re.compile(
    r"<think>.*?</think>",
    flags=re.DOTALL | re.IGNORECASE,
)

# Beberapa model pakai <thinking> (plural)
_THINKING_TAG_PATTERN = re.compile(
    r"<thinking>.*?</thinking>",
    flags=re.DOTALL | re.IGNORECASE,
)

# Reasoning prefix tanpa closing tag (edge case)
_REASONING_PREFIX_PATTERN = re.compile(
    r"^(Okay,\s+I need to|Let me think|I'll analyze|First,?\s+let me).*?\n\n",
    flags=re.DOTALL | re.IGNORECASE,
)


def strip_thinking_tags(text: str) -> str:
    """
    Hapus semua thinking/reasoning block dari LLM output.

    Handles:
    - <think>...</think>       Qwen3, beberapa OpenRouter models
    - <thinking>...</thinking> Variasi lain
    - Reasoning prefix tanpa tag (best-effort)

    Args:
        text: Raw LLM output

    Returns:
        Clean text tanpa thinking artifacts
    """
    if not text:
        return text

    # Strip tag-based thinking blocks
    text = _THINK_TAG_PATTERN.sub("", text)
    text = _THINKING_TAG_PATTERN.sub("", text)

    # Normalize whitespace yang tersisa setelah strip
    # (biasanya ada newline ganda di awal)
    text = text.strip()

    # Kalau setelah strip jadi kosong, return string kosong
    # (biarkan router fallback ke model berikutnya)
    return text


def clean_llm_output(text: str, max_chars: Optional[int] = None) -> str:
    """
    Full post-processing pipeline untuk LLM output.

    Steps:
    1. Strip thinking tags
    2. Normalize whitespace berlebihan
    3. Truncate jika terlalu panjang (optional)

    Args:
        text    : Raw LLM output
        max_chars: Truncate jika lebih dari ini. None = tidak truncate

    Returns:
        Cleaned text
    """
    if not text:
        return text

    # Step 1: Strip thinking tags
    text = strip_thinking_tags(text)

    # Step 2: Normalize whitespace
    # Hapus lebih dari 2 newline berturut-turut
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Hapus trailing whitespace per baris
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = text.strip()

    # Step 3: Truncate kalau perlu
    if max_chars and len(text) > max_chars:
        # Cari titik potong yang bersih (di akhir kalimat/paragraf)
        cutoff = text.rfind("\n", 0, max_chars)
        if cutoff == -1 or cutoff < max_chars * 0.8:
            cutoff = max_chars
        text = text[:cutoff].rstrip() + "\n\n_(Respons dipotong karena terlalu panjang)_"

    return text