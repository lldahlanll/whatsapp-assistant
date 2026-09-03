"""Firewall filter and NAT inspection tools."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_firewall_rules(client: MikroTikRestClient) -> list[dict[str, Any]]:
    """Retrieve firewall filter rules.

    Queries: `/ip/firewall/filter`
    """
    raw_rules = await client.get("ip/firewall/filter")
    items = raw_rules if isinstance(raw_rules, list) else [raw_rules]

    rules: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        disabled = item.get("disabled") == "true" or item.get("disabled") is True
        rules.append({
            "chain": item.get("chain", "forward"),
            "action": item.get("action", "accept"),
            "protocol": item.get("protocol"),
            "src_address": item.get("src-address") or item.get("src-address-list"),
            "dst_address": item.get("dst-address") or item.get("dst-address-list"),
            "src_port": item.get("src-port"),
            "dst_port": item.get("dst-port"),
            "in_interface": item.get("in-interface") or item.get("in-interface-list"),
            "out_interface": item.get("out-interface") or item.get("out-interface-list"),
            "packets": int(item.get("packets", 0)),
            "bytes": int(item.get("bytes", 0)),
            "disabled": disabled,
            "comment": item.get("comment", ""),
        })

    return rules


async def get_nat_rules(client: MikroTikRestClient) -> list[dict[str, Any]]:
    """Retrieve firewall NAT rules.

    Queries: `/ip/firewall/nat`
    """
    raw_rules = await client.get("ip/firewall/nat")
    items = raw_rules if isinstance(raw_rules, list) else [raw_rules]

    rules: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        disabled = item.get("disabled") == "true" or item.get("disabled") is True
        rules.append({
            "chain": item.get("chain", "srcnat"),
            "action": item.get("action", "masquerade"),
            "protocol": item.get("protocol"),
            "src_address": item.get("src-address"),
            "dst_address": item.get("dst-address"),
            "dst_port": item.get("dst-port"),
            "out_interface": item.get("out-interface") or item.get("out-interface-list"),
            "in_interface": item.get("in-interface") or item.get("in-interface-list"),
            "to_addresses": item.get("to-addresses"),
            "to_ports": item.get("to-ports"),
            "packets": int(item.get("packets", 0)),
            "bytes": int(item.get("bytes", 0)),
            "disabled": disabled,
            "comment": item.get("comment", ""),
        })

    return rules
