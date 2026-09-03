"""System health and resource tool."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_system_health(client: MikroTikRestClient) -> dict[str, Any]:
    """Retrieve system health and resource metrics from MikroTik.

    Queries:
    - `/system/resource`
    - `/system/health` (optional, for temperature/voltage)
    - `/system/routerboard` (optional, for model/firmware)
    """
    resource_raw = await client.get("system/resource")
    resource: dict[str, Any] = (
        resource_raw[0] if isinstance(resource_raw, list) and resource_raw else (
            resource_raw if isinstance(resource_raw, dict) else {}
        )
    )

    # Optional health sensors (temperature, voltage)
    temperature: float | None = None
    voltage: float | None = None
    try:
        health_raw = await client.get("system/health")
        health_items = health_raw if isinstance(health_raw, list) else [health_raw]
        for item in health_items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").lower()
            val = item.get("value")
            if "temperature" in name or "temp" in name:
                try:
                    temperature = float(val or 0)
                except (ValueError, TypeError):
                    pass
            elif "voltage" in name:
                try:
                    voltage = float(val or 0)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    # Optional routerboard details
    board_model: str = resource.get("board-name", resource.get("platform", "MikroTik"))
    firmware: str | None = None
    try:
        rb_raw = await client.get("system/routerboard")
        rb = rb_raw[0] if isinstance(rb_raw, list) and rb_raw else (
            rb_raw if isinstance(rb_raw, dict) else {}
        )
        if rb.get("model"):
            board_model = str(rb.get("model"))
        firmware = rb.get("current-firmware") or rb.get("upgrade-firmware")
    except Exception:
        pass

    total_memory = int(resource.get("total-memory", 0))
    free_memory = int(resource.get("free-memory", 0))
    used_memory = max(0, total_memory - free_memory)
    memory_usage_pct = round((used_memory / total_memory * 100), 1) if total_memory > 0 else 0.0

    total_hdd = int(resource.get("total-hdd-space", 0))
    free_hdd = int(resource.get("free-hdd-space", 0))
    used_hdd = max(0, total_hdd - free_hdd)
    hdd_usage_pct = round((used_hdd / total_hdd * 100), 1) if total_hdd > 0 else 0.0

    return {
        "version": resource.get("version", "Unknown"),
        "board_name": board_model,
        "platform": resource.get("platform", "MikroTik"),
        "uptime": resource.get("uptime", "Unknown"),
        "cpu_load": int(resource.get("cpu-load", 0)),
        "cpu_count": int(resource.get("cpu-count", 1)),
        "cpu_frequency": resource.get("cpu-frequency"),
        "memory": {
            "total_bytes": total_memory,
            "free_bytes": free_memory,
            "used_bytes": used_memory,
            "usage_pct": memory_usage_pct,
        },
        "hdd": {
            "total_bytes": total_hdd,
            "free_bytes": free_hdd,
            "used_bytes": used_hdd,
            "usage_pct": hdd_usage_pct,
        },
        "temperature": temperature,
        "voltage": voltage,
        "firmware": firmware,
        "bad_blocks": resource.get("bad-blocks"),
    }
