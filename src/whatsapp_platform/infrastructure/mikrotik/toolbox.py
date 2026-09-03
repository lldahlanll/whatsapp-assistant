"""NetworkToolbox — high-level facade coordinating MikroTik tools, caching, and audit logging."""

from __future__ import annotations

import time
from typing import Any

import structlog

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.mikrotik.cache import MikroTikCache
from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient
from whatsapp_platform.infrastructure.mikrotik.tools.connections import get_active_connections
from whatsapp_platform.infrastructure.mikrotik.tools.dhcp import get_dhcp_leases
from whatsapp_platform.infrastructure.mikrotik.tools.dns import get_dns_status
from whatsapp_platform.infrastructure.mikrotik.tools.firewall import (
    get_firewall_rules,
    get_nat_rules,
)
from whatsapp_platform.infrastructure.mikrotik.tools.health_score import calculate_health_score
from whatsapp_platform.infrastructure.mikrotik.tools.interfaces import (
    get_interface_traffic,
    get_interfaces,
)
from whatsapp_platform.infrastructure.mikrotik.tools.logs import get_logs
from whatsapp_platform.infrastructure.mikrotik.tools.routing import get_routes
from whatsapp_platform.infrastructure.mikrotik.tools.security import security_audit
from whatsapp_platform.infrastructure.mikrotik.tools.system import get_system_health

logger = structlog.get_logger()


class NetworkToolbox:
    """Read-only orchestration toolbox for MikroTik RouterOS insights."""

    def __init__(
        self,
        client: MikroTikRestClient,
        cache: MikroTikCache,
        settings: Settings,
    ) -> None:
        self._client = client
        self._cache = cache
        self._settings = settings

    @property
    def client(self) -> MikroTikRestClient:
        return self._client

    @property
    def is_enabled(self) -> bool:
        return self._client.is_enabled

    def _log_audit(
        self,
        tool_name: str,
        user_jid: str | None,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Write structured audit log for every network tool execution."""
        logger.info(
            "mikrotik_tool_call",
            tool=tool_name,
            user=user_jid or "system",
            router_host=self._settings.mikrotik_host,
            duration_ms=round(duration_ms, 2),
            success=success,
            error=error,
        )

    # -------------------------------------------------------------
    # High-level tool methods with caching & audit logs
    # -------------------------------------------------------------

    async def get_health_report(self, user_jid: str | None = None) -> dict[str, Any]:
        """Fetch comprehensive network health report with health score."""
        start = time.monotonic()
        cache_key = "health_report"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        try:
            system = await get_system_health(self._client)
            interfaces = await get_interfaces(self._client)
            firewall = await get_firewall_rules(self._client)
            dns = await get_dns_status(self._client)
            dhcp = await get_dhcp_leases(self._client)

            health_score_data = calculate_health_score({
                "system": system,
                "interfaces": interfaces,
                "firewall": firewall,
                "dns": dns,
                "dhcp": dhcp,
            })

            report = {
                "system": system,
                "interfaces_count": len(interfaces),
                "running_interfaces": sum(1 for i in interfaces if i.get("running")),
                "active_dhcp_count": len(dhcp),
                "firewall_rules_count": len(firewall),
                "health_score": health_score_data,
                "timestamp": time.time(),
            }

            await self._cache.set(cache_key, report, self._settings.network_cache_ttl_system)
            self._log_audit(
                "get_health_report", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return report

        except Exception as exc:
            self._log_audit(
                "get_health_report", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_traffic_report(
        self,
        interface_name: str | None = None,
        user_jid: str | None = None,
    ) -> dict[str, Any]:
        """Fetch real-time traffic report (short/no cache for live values)."""
        start = time.monotonic()
        try:
            report = await get_interface_traffic(self._client, interface_name=interface_name)
            self._log_audit(
                "get_traffic_report", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return report
        except Exception as exc:
            self._log_audit(
                "get_traffic_report", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_security_report(self, user_jid: str | None = None) -> dict[str, Any]:
        """Run network security audit assessment."""
        start = time.monotonic()
        cache_key = "security_audit"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        try:
            report = await security_audit(self._client)
            await self._cache.set(cache_key, report, ttl_seconds=60.0)
            self._log_audit(
                "security_audit", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return report
        except Exception as exc:
            self._log_audit(
                "security_audit", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_dhcp_report(
        self,
        query: str | None = None,
        user_jid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch active DHCP leases."""
        start = time.monotonic()
        cache_key = f"dhcp_leases_{query or 'all'}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        try:
            report = await get_dhcp_leases(self._client, filter_query=query)
            await self._cache.set(cache_key, report, self._settings.network_cache_ttl_dhcp)
            self._log_audit(
                "get_dhcp_leases", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return report
        except Exception as exc:
            self._log_audit(
                "get_dhcp_leases", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_firewall_report(self, user_jid: str | None = None) -> dict[str, Any]:
        """Fetch firewall filter and NAT rules."""
        start = time.monotonic()
        cache_key = "firewall_report"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        try:
            filters = await get_firewall_rules(self._client)
            nat = await get_nat_rules(self._client)
            report = {
                "filter_rules": filters,
                "nat_rules": nat,
                "total_filters": len(filters),
                "total_nat": len(nat),
            }
            await self._cache.set(cache_key, report, self._settings.network_cache_ttl_firewall)
            self._log_audit(
                "get_firewall_rules", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return report
        except Exception as exc:
            self._log_audit(
                "get_firewall_rules", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_routes_report(self, user_jid: str | None = None) -> list[dict[str, Any]]:
        """Fetch IP routing table."""
        start = time.monotonic()
        cache_key = "routes_report"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        try:
            routes = await get_routes(self._client)
            await self._cache.set(cache_key, routes, self._settings.network_cache_ttl_routes)
            self._log_audit(
                "get_routes", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return routes
        except Exception as exc:
            self._log_audit(
                "get_routes", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_logs_report(
        self,
        limit: int = 20,
        topic: str | None = None,
        user_jid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent system logs."""
        start = time.monotonic()
        try:
            logs = await get_logs(self._client, limit=limit, topic_filter=topic)
            self._log_audit(
                "get_logs", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return logs
        except Exception as exc:
            self._log_audit(
                "get_logs", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

    async def get_connections_report(self, user_jid: str | None = None) -> dict[str, Any]:
        """Fetch aggregated connection tracking stats."""
        start = time.monotonic()
        try:
            conns = await get_active_connections(self._client)
            self._log_audit(
                "get_active_connections", user_jid, (time.monotonic() - start) * 1000, success=True
            )
            return conns
        except Exception as exc:
            self._log_audit(
                "get_active_connections", user_jid, (time.monotonic() - start) * 1000, success=False, error=str(exc)
            )
            raise

