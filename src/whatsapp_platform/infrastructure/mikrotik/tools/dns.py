"""DNS configuration and status tool."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def get_dns_status(client: MikroTikRestClient) -> dict[str, Any]:
    """Retrieve DNS settings and cache metrics.

    Queries: `/ip/dns`
    """
    raw_dns = await client.get("ip/dns")
    dns: dict[str, Any] = (
        raw_dns[0] if isinstance(raw_dns, list) and raw_dns else (
            raw_dns if isinstance(raw_dns, dict) else {}
        )
    )

    servers = dns.get("servers", "")
    dynamic_servers = dns.get("dynamic-servers", "")
    allow_remote = (
        dns.get("allow-remote-requests") == "true" or dns.get("allow-remote-requests") is True
    )

    return {
        "servers": servers.split(",") if servers else [],
        "dynamic_servers": dynamic_servers.split(",") if dynamic_servers else [],
        "allow_remote_requests": allow_remote,
        "cache_size_kb": int(dns.get("cache-size", 0)),
        "cache_used_kb": int(dns.get("cache-used", 0)),
        "doh_server": dns.get("use-doh-server", ""),
        "doh_max_concurrent_queries": dns.get("doh-max-concurrent-queries"),
    }
