"""Phone number extraction and normalization utility for Customer Lookup."""

import re

# Regex matching candidate phone numbers:
# Optional +62, 62, or 0 prefix, followed by 8 to 13 digits starting with 2-8,
# separated by optional spaces, hyphens (-), or dots (.).
PHONE_REGEX = re.compile(r"(?<!\d)(?:\+?62|0)?[\s\.-]*([2-8](?:[\s\.-]*\d){7,12})(?!\d)")


def normalize_phone(raw: str) -> str | None:
    """Normalize a raw phone number input into a validated core phone string.

    Strips non-digit characters (+, -, ., spaces) and standard prefixes (+62, 62, 0).
    Validates that the resulting core phone string is 8-13 digits long
    and starts with a digit in 2-8.

    Args:
        raw: Raw phone string (e.g. "+62 896-1234-5678", "0896.1234.5678", "08123456789")

    Returns:
        Normalized core string (e.g. "89612345678") or None if invalid.
    """
    if not raw:
        return None

    # Remove all non-digits
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    # Strip prefixes in priority order: 62, then 0
    if digits.startswith("62"):
        core = digits[2:]
    elif digits.startswith("0"):
        core = digits[1:]
    elif digits.startswith("8"):
        core = digits
    else:
        # If no 62/0 prefix, core MUST start with 8 (mobile number) to avoid dates like 20260510
        return None

    # Validate core phone length (8..13) and first digit (2..8)
    if 8 <= len(core) <= 13 and core[0] in "2345678":
        return core

    return None


def extract_phone_cores(text: str) -> list[str]:
    """Extract, normalize, deduplicate, and limit phone number cores from text.

    Args:
        text: Inbound message text.

    Returns:
        List of unique normalized phone core strings, capped at a maximum of 5 items.
    """
    if not text:
        return []

    seen: set[str] = set()
    cores: list[str] = []

    for match in PHONE_REGEX.finditer(text):
        raw_match = match.group(0)
        normalized = normalize_phone(raw_match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cores.append(normalized)
            if len(cores) >= 5:
                break

    return cores
