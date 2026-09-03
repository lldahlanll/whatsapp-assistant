"""Interface statistics and traffic monitoring tools."""

from __future__ import annotations

import time
from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_interfaces(client: MikroTikRestClient) -> list[dict[str, Any]]:
    """Retrieve structured interface status and summary metrics.

    Queries: `/interface`
    """
    raw_interfaces = await client.get("interface")
    items = raw_interfaces if isinstance(raw_interfaces, list) else [raw_interfaces]

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        name = item.get("name", "unknown")
        if_type = item.get("type", "unknown")
        running = item.get("running") == "true" or item.get("running") is True
        disabled = item.get("disabled") == "true" or item.get("disabled") is True

        rx_byte = int(item.get("rx-byte", 0))
        tx_byte = int(item.get("tx-byte", 0))
        rx_packet = int(item.get("rx-packet", 0))
        tx_packet = int(item.get("tx-packet", 0))
        rx_error = int(item.get("rx-error", 0))
        tx_error = int(item.get("tx-error", 0))
        rx_drop = int(item.get("rx-drop", 0))
        tx_drop = int(item.get("tx-drop", 0))

        results.append({
            "name": name,
            "type": if_type,
            "running": running,
            "enabled": not disabled,
            "comment": item.get("comment", ""),
            "mac_address": item.get("mac-address"),
            "traffic": {
                "rx_bytes": rx_byte,
                "tx_bytes": tx_byte,
                "rx_packets": rx_packet,
                "tx_packets": tx_packet,
            },
            "health": {
                "rx_errors": rx_error,
                "tx_errors": tx_error,
                "rx_drops": rx_drop,
                "tx_drops": tx_drop,
            },
        })

    return results


async def get_interface_traffic(
    client: MikroTikRestClient,
    interface_name: str | None = None,
) -> dict[str, Any]:
    """Retrieve traffic / bandwidth metrics for interfaces.

    If interface_name is None, attempts to detect WAN (or returns top active interfaces).
    """
    interfaces = await get_interfaces(client)

    target_interfaces = interfaces
    if interface_name:
        target_interfaces = [
            iface for iface in interfaces if iface["name"].lower() == interface_name.lower()
        ]
        if not target_interfaces:
            # Try partial match
            target_interfaces = [
                iface for iface in interfaces if interface_name.lower() in iface["name"].lower()
            ]

    # If no specific interface specified, prioritize running WAN / ether1 / pppoe / bridge
    if not interface_name:
        wan_candidates = [
            iface for iface in interfaces
            if iface["running"] and (
                "wan" in iface["name"].lower()
                or "ether1" in iface["name"].lower()
                or "internet" in iface["name"].lower()
                or iface["type"] in ("pppoe-out", "ether")
            )
        ]
        if wan_candidates:
            target_interfaces = wan_candidates[:3]

    timestamp = time.time()
    return {
        "timestamp": timestamp,
        "interfaces": target_interfaces,
        "total_interfaces": len(interfaces),
    }
