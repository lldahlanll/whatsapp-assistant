"""MikroTik Read-Only Tools Package."""

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

__all__ = [
    "calculate_health_score",
    "get_active_connections",
    "get_dhcp_leases",
    "get_dns_status",
    "get_firewall_rules",
    "get_interface_traffic",
    "get_interfaces",
    "get_logs",
    "get_nat_rules",
    "get_routes",
    "get_system_health",
    "security_audit",
]
