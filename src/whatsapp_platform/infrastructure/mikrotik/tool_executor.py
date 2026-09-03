"""MikroTik Tool Executor — executes tool calls from LLM with permission guards and JSON output."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.features.network.permission import NetworkPermissionChecker
from whatsapp_platform.infrastructure.mikrotik.toolbox import NetworkToolbox

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID

logger = structlog.get_logger()


def _clean_dhcp_leases(raw_leases: Any) -> dict[str, Any]:
    """Shape DHCP lease data into compact summary and device list."""
    if not isinstance(raw_leases, list):
        return {"total_devices_count": 0, "bound_devices_count": 0, "devices": []}

    cleaned: list[dict[str, Any]] = []
    for lease in raw_leases:
        if not isinstance(lease, dict):
            continue
        ip = lease.get("address") or lease.get("active-address") or ""
        mac = lease.get("mac-address") or lease.get("active-mac-address") or ""
        host = lease.get("host-name") or lease.get("comment") or ""
        status = lease.get("status") or ("bound" if lease.get("active-address") else "unknown")
        entry: dict[str, Any] = {"ip": ip, "mac": mac, "hostname": host, "status": status}
        if lease.get("server"):
            entry["server"] = lease.get("server")
        cleaned.append(entry)

    total = len(cleaned)
    bound_count = sum(1 for c in cleaned if c.get("status") in ("bound", "active"))

    return {
        "total_devices_count": total,
        "bound_devices_count": bound_count,
        "devices": cleaned[:35],
        "has_more": total > 35,
    }


def _clean_firewall_report(report: Any) -> dict[str, Any]:
    """Clean firewall report to prevent massive token dumps."""
    if not isinstance(report, dict):
        return {"summary": "No firewall data available"}

    filters = report.get("filter_rules") or []
    nat = report.get("nat_rules") or []

    clean_filters = []
    for f in filters[:15]:
        if isinstance(f, dict):
            clean_filters.append({
                "chain": f.get("chain"),
                "action": f.get("action"),
                "comment": f.get("comment", ""),
                "disabled": f.get("disabled", False),
            })

    clean_nat = []
    for n in nat[:15]:
        if isinstance(n, dict):
            clean_nat.append({
                "chain": n.get("chain"),
                "action": n.get("action"),
                "to_addresses": n.get("to-addresses"),
                "comment": n.get("comment", ""),
            })

    return {
        "total_filter_rules": report.get("total_filters", len(filters)),
        "total_nat_rules": report.get("total_nat", len(nat)),
        "sample_filter_rules": clean_filters,
        "sample_nat_rules": clean_nat,
    }


def _clean_routes_report(routes: Any) -> list[dict[str, Any]]:
    """Clean routing table data to essential fields."""
    if not isinstance(routes, list):
        return []
    cleaned = []
    for r in routes[:15]:
        if isinstance(r, dict):
            cleaned.append({
                "dst_address": r.get("dst_address") or r.get("dst-address"),
                "gateway": r.get("gateway") or "local",
                "active": r.get("active", False),
                "distance": r.get("distance"),
            })
    return cleaned


class MikroTikToolExecutor:
    """Dispatches tool calls requested by LLM to NetworkToolbox methods."""

    def __init__(
        self,
        toolbox: NetworkToolbox,
        permission_checker: NetworkPermissionChecker,
    ) -> None:
        self._toolbox = toolbox
        self._permission_checker = permission_checker

    @property
    def is_enabled(self) -> bool:
        """Return whether MikroTik integration is enabled."""
        return self._toolbox.is_enabled

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
    ) -> str:
        """Execute a tool call requested by LLM and return JSON string response.

        Guards:
        1. Permission guard via NetworkPermissionChecker
        2. MikroTik enabled guard
        """
        user_jid_str = str(user_jid)
        chat_jid_str = str(chat_jid)

        # 1. Permission Guard
        if not self._permission_checker.has_network_read_permission(user_jid, chat_jid):
            logger.warning(
                "MikroTik tool call rejected: permission denied",
                tool=tool_name,
                user=user_jid_str,
                chat=chat_jid_str,
            )
            return json.dumps({
                "status": "error",
                "error": "Izin ditolak: Pengguna tidak memiliki akses untuk melihat data jaringan router MikroTik.",
            })

        # 2. Enabled Guard
        if not self._toolbox.is_enabled:
            return json.dumps({
                "status": "error",
                "error": "Fitur MikroTik sedang dinonaktifkan pada konfigurasi sistem.",
            })

        logger.info(
            "Executing MikroTik tool call from LLM",
            tool=tool_name,
            arguments=arguments,
            user=user_jid_str,
            chat=chat_jid_str,
        )

        try:
            result: dict[str, Any] | list[dict[str, Any]] = {}
            if tool_name == "mikrotik_get_health":
                result = await self._toolbox.get_health_report(user_jid=user_jid_str)

            elif tool_name == "mikrotik_get_traffic":
                iface = arguments.get("interface_name")
                result = await self._toolbox.get_traffic_report(interface_name=iface, user_jid=user_jid_str)

            elif tool_name == "mikrotik_get_dhcp_leases":
                query = arguments.get("query")
                raw_leases = await self._toolbox.get_dhcp_report(query=query, user_jid=user_jid_str)
                result = _clean_dhcp_leases(raw_leases)

            elif tool_name == "mikrotik_audit_security":
                result = await self._toolbox.get_security_report(user_jid=user_jid_str)

            elif tool_name == "mikrotik_get_firewall":
                raw_fw = await self._toolbox.get_firewall_report(user_jid=user_jid_str)
                result = _clean_firewall_report(raw_fw)

            elif tool_name == "mikrotik_get_routes":
                raw_routes = await self._toolbox.get_routes_report(user_jid=user_jid_str)
                result = _clean_routes_report(raw_routes)

            elif tool_name == "mikrotik_get_logs":
                limit_val = arguments.get("limit")
                try:
                    limit = min(int(limit_val), 20) if limit_val is not None else 15
                except (ValueError, TypeError):
                    limit = 15
                topic = arguments.get("topic")
                result = await self._toolbox.get_logs_report(limit=limit, topic=topic, user_jid=user_jid_str)

            elif tool_name == "mikrotik_get_connections":
                result = await self._toolbox.get_connections_report(user_jid=user_jid_str)

            else:
                return json.dumps({
                    "status": "error",
                    "error": f"Tool '{tool_name}' tidak dikenali.",
                })

            return json.dumps({"status": "success", "data": result}, ensure_ascii=False, default=str)

        except Exception as exc:
            logger.error(
                "Error executing MikroTik tool call",
                tool=tool_name,
                error=str(exc),
                exc_info=True,
            )
            return json.dumps({
                "status": "error",
                "error": f"Gagal mengeksekusi tool {tool_name}: {exc}",
            }, ensure_ascii=False)
