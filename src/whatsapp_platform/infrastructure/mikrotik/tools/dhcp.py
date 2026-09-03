"""DHCP lease monitoring tool."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_dhcp_leases(
    client: MikroTikRestClient,
    filter_query: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve DHCP server leases from MikroTik.

    Queries: `/ip/dhcp-server/lease`
    Supports optional search/filtering by IP, MAC, hostname, or comment.
    """
    raw_leases = await client.get("ip/dhcp-server/lease")
    items = raw_leases if isinstance(raw_leases, list) else [raw_leases]

    leases: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        address = item.get("address", "")
        mac_address = item.get("mac-address", "")
        hostname = item.get("host-name", "")
        status = item.get("status", "bound")
        comment = item.get("comment", "")
        server = item.get("server", "")
        expires_after = item.get("expires-after", "")
        dynamic = item.get("dynamic") == "true" or item.get("dynamic") is True
        disabled = item.get("disabled") == "true" or item.get("disabled") is True

        lease_entry = {
            "address": address,
            "mac_address": mac_address,
            "hostname": hostname,
            "status": status,
            "server": server,
            "expires_after": expires_after,
            "dynamic": dynamic,
            "disabled": disabled,
            "comment": comment,
        }

        if filter_query:
            query = filter_query.lower()
            if (
                query in address.lower()
                or query in mac_address.lower()
                or query in hostname.lower()
                or query in comment.lower()
            ):
                leases.append(lease_entry)
        else:
            leases.append(lease_entry)

    return leases
