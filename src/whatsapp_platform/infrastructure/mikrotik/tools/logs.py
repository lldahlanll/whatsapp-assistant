"""System log inspection tool."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_logs(
    client: MikroTikRestClient,
    limit: int = 20,
    topic_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve system logs from MikroTik with safety limit and filtering.

    Queries: `/log`
    """
    safe_limit = min(max(1, limit), 50)  # Safe bound: 1 to 50
    raw_logs = await client.get("log")
    items = raw_logs if isinstance(raw_logs, list) else [raw_logs]

    # MikroTik logs are usually chronological (oldest to newest), reverse to get newest first
    reversed_items = list(reversed(items))

    filtered_logs: list[dict[str, Any]] = []
    for item in reversed_items:
        if not isinstance(item, dict):
            continue

        topics = item.get("topics", "")
        message = item.get("message", "")
        log_time = item.get("time", "")

        if topic_filter:
            tf = topic_filter.lower()
            if tf not in topics.lower() and tf not in message.lower():
                continue

        filtered_logs.append({
            "time": log_time,
            "topics": topics,
            "message": message,
        })

        if len(filtered_logs) >= safe_limit:
            break

    return filtered_logs
