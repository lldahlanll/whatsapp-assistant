"""IP routing inspection tool."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_routes(client: MikroTikRestClient) -> list[dict[str, Any]]:
    """Retrieve IP routes from MikroTik.

    Queries: `/ip/route`
    """
    raw_routes = await client.get("ip/route")
    items = raw_routes if isinstance(raw_routes, list) else [raw_routes]

    routes: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        active = item.get("active") == "true" or item.get("active") is True
        disabled = item.get("disabled") == "true" or item.get("disabled") is True
        dynamic = item.get("dynamic") == "true" or item.get("dynamic") is True

        routes.append({
            "dst_address": item.get("dst-address", "0.0.0.0/0"),
            "gateway": item.get("gateway", ""),
            "distance": int(item.get("distance", 1)),
            "active": active,
            "disabled": disabled,
            "dynamic": dynamic,
            "routing_table": item.get("routing-table", "main"),
            "comment": item.get("comment", ""),
        })

    return routes
