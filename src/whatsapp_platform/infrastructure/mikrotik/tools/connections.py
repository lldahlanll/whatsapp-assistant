"""Connection tracking and aggregation tool."""

from __future__ import annotations

from collections import Counter
from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_active_connections(client: MikroTikRestClient, sample_limit: int = 200) -> dict[str, Any]:
    """Retrieve aggregated connection tracking data.

    Queries: `/ip/firewall/connection`
    Summarizes protocol distribution, top sources, top destinations without dumping raw lines.
    """
    raw_conns = await client.get("ip/firewall/connection")
    items = raw_conns if isinstance(raw_conns, list) else [raw_conns]

    total_connections = len(items)

    protocol_counter: Counter[str] = Counter()
    src_counter: Counter[str] = Counter()
    dst_counter: Counter[str] = Counter()

    for item in items[:sample_limit]:
        if not isinstance(item, dict):
            continue

        proto = item.get("protocol", "unknown")
        src = item.get("src-address", "").split(":")[0]
        dst = item.get("dst-address", "").split(":")[0]

        if proto:
            protocol_counter[proto] += 1
        if src:
            src_counter[src] += 1
        if dst:
            dst_counter[dst] += 1

    top_sources = [
        {"ip": ip, "count": count} for ip, count in src_counter.most_common(5)
    ]
    top_destinations = [
        {"ip": ip, "count": count} for ip, count in dst_counter.most_common(5)
    ]
    protocol_distribution = dict(protocol_counter.most_common(5))

    return {
        "total_connections": total_connections,
        "sample_analyzed": min(total_connections, sample_limit),
        "protocol_distribution": protocol_distribution,
        "top_sources": top_sources,
        "top_destinations": top_destinations,
    }
