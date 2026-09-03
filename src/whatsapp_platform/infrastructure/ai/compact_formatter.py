"""Compact Tool Result Formatter.

Transforms raw API JSON responses (MikroTik, Finance) into compact internal representations,
filtering out unnecessary keys, passwords, and noise before sending to the LLM.
Enforces MAX_TOOL_RESULT_CHARS protection.
"""

from __future__ import annotations

import json
from typing import Any


def compact_tool_result(tool_name: str, raw_output: str, max_chars: int = 1000) -> str:
    """Format and compact raw tool output string into lightweight JSON/text for LLM.

    Args:
        tool_name: Name of the tool executed.
        raw_output: Raw JSON or text output from tool executor.
        max_chars: Maximum character limit budget.

    Returns:
        Compacted string representation within max_chars.
    """
    if not raw_output:
        return json.dumps({"status": "ok", "result": None})

    try:
        data = json.loads(raw_output)
    except Exception:
        # Non-JSON raw text output
        return _truncate_string(raw_output, max_chars)

    if not isinstance(data, dict):
        return _truncate_string(json.dumps(data, ensure_ascii=False), max_chars)

    # If already an error response, preserve error message
    if data.get("status") == "error":
        compact_err = {
            "status": "error",
            "error": data.get("error") or data.get("message") or "Unknown error",
        }
        return json.dumps(compact_err, ensure_ascii=False)

    # Domain specific compacting
    if tool_name.startswith("mikrotik_"):
        compacted_obj = _compact_mikrotik_result(tool_name, data)
    elif tool_name.startswith("finance_"):
        compacted_obj = _compact_finance_result(tool_name, data)
    else:
        compacted_obj = _strip_empty_keys(data)

    compact_json = json.dumps(compacted_obj, ensure_ascii=False)
    return _truncate_string(compact_json, max_chars)


def _compact_mikrotik_result(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Compact MikroTik API response object."""
    # Filter logs: keep only last 5 entries
    if tool_name == "mikrotik_get_logs" and "logs" in data:
        logs = data.get("logs", [])
        if isinstance(logs, list):
            data["logs"] = logs[-5:]
            data["total_log_count"] = len(logs)

    # Filter DHCP leases: extract relevant fields (ip, mac, host_name, status)
    if tool_name == "mikrotik_get_dhcp_leases" and "leases" in data:
        leases = data.get("leases", [])
        if isinstance(leases, list):
            compact_leases = []
            for lease in leases[:10]:  # Cap at 10 active leases
                if isinstance(lease, dict):
                    compact_leases.append({
                        "address": lease.get("address") or lease.get("active-address"),
                        "mac": lease.get("mac-address") or lease.get("active-mac-address"),
                        "host_name": lease.get("host-name") or lease.get("comment"),
                        "status": lease.get("status"),
                    })
            data["leases"] = compact_leases

    # Strip passwords, credentials, sensitive config if present
    return _strip_sensitive_keys(data)


def _compact_finance_result(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Compact Finance API response object."""
    # Filter transaction lists: limit to top 5 items
    if "transactions" in data and isinstance(data["transactions"], list):
        txs = data["transactions"]
        compact_txs = []
        for tx in txs[:5]:
            if isinstance(tx, dict):
                compact_txs.append({
                    "id": tx.get("id"),
                    "amount": tx.get("amount"),
                    "type": tx.get("type"),
                    "desc": tx.get("description"),
                    "account": tx.get("account_name"),
                    "date": str(tx.get("created_at", ""))[:10],
                })
        data["transactions"] = compact_txs

    return _strip_empty_keys(data)


def _strip_sensitive_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Remove passwords, secrets, and raw tokens from dictionary recursively."""
    sensitive_words = {"password", "secret", "token", "passphrase", "api_key"}
    cleaned = {}
    for k, v in data.items():
        if any(sw in k.lower() for sw in sensitive_words):
            continue
        if isinstance(v, dict):
            cleaned[k] = _strip_sensitive_keys(v)
        elif isinstance(v, list):
            cleaned[k] = [
                _strip_sensitive_keys(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned


def _strip_empty_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None and empty string values to save characters."""
    return {k: v for k, v in data.items() if v is not None and v != ""}


def _truncate_string(text: str, max_chars: int) -> str:
    """Truncate text safely at max_chars budget."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 18] + "... [truncated]"
