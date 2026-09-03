"""Network Health Score Calculator."""

from __future__ import annotations

from typing import Any


def calculate_health_score(metrics: dict[str, Any]) -> dict[str, Any]:
    """Calculate transparent 0-100 Network Health Score based on weighted metrics.

    Weights:
    - System Health (CPU, Uptime): 20%
    - WAN Health (Link Status): 25%
    - Interface Health (Errors/Drops): 15%
    - Firewall Status: 15%
    - DNS Status: 10%
    - DHCP Status: 5%
    - Resource Storage/RAM: 10%
    """
    scores: dict[str, float] = {}
    details: dict[str, str] = {}

    system = metrics.get("system")
    interfaces = metrics.get("interfaces", [])
    firewall = metrics.get("firewall", [])
    dns = metrics.get("dns")
    dhcp = metrics.get("dhcp", [])

    # 1. System Health (20%)
    if system and isinstance(system, dict):
        cpu_load = system.get("cpu_load", 0)
        if cpu_load < 50:
            scores["system"] = 20.0
            details["system"] = f"CPU normal ({cpu_load}%)"
        elif cpu_load < 80:
            scores["system"] = 14.0
            details["system"] = f"CPU moderat ({cpu_load}%)"
        else:
            scores["system"] = 6.0
            details["system"] = f"CPU tinggi ({cpu_load}%)"
    else:
        scores["system"] = 0.0
        details["system"] = "UNKNOWN"

    # 2. WAN Health (25%)
    wan_iface = None
    for iface in interfaces:
        name = iface.get("name", "").lower()
        if iface.get("running") and (
            "wan" in name or "ether1" in name or "internet" in name or iface.get("type") == "pppoe-out"
        ):
            wan_iface = iface
            break

    if wan_iface:
        scores["wan"] = 25.0
        details["wan"] = f"Link UP ({wan_iface.get('name')})"
    elif interfaces:
        # Check any running interface
        running_count = sum(1 for iface in interfaces if iface.get("running"))
        if running_count > 0:
            scores["wan"] = 20.0
            details["wan"] = f"{running_count} interface aktif"
        else:
            scores["wan"] = 5.0
            details["wan"] = "Tidak ada interface aktif"
    else:
        scores["wan"] = 0.0
        details["wan"] = "UNKNOWN"

    # 3. Interface Health (15%) - Errors and Drops
    if interfaces:
        total_errors = sum(
            iface.get("health", {}).get("rx_errors", 0) + iface.get("health", {}).get("tx_errors", 0)
            for iface in interfaces
        )
        total_drops = sum(
            iface.get("health", {}).get("rx_drops", 0) + iface.get("health", {}).get("tx_drops", 0)
            for iface in interfaces
        )
        if total_errors == 0 and total_drops < 100:
            scores["interface"] = 15.0
            details["interface"] = "Bersih dari error/packet drop"
        elif total_errors < 10 and total_drops < 1000:
            scores["interface"] = 10.0
            details["interface"] = f"Minor error/drops ({total_errors} err, {total_drops} drop)"
        else:
            scores["interface"] = 4.0
            details["interface"] = f"Banyak error/drop ({total_errors} err, {total_drops} drop)"
    else:
        scores["interface"] = 0.0
        details["interface"] = "UNKNOWN"

    # 4. Firewall (15%) - Basic protection check
    if firewall and isinstance(firewall, list):
        has_drop_invalid = any(
            r.get("action") == "drop" and "invalid" in str(r.get("comment", "")).lower()
            for r in firewall if not r.get("disabled")
        )
        has_input_rules = any(
            r.get("chain") == "input" for r in firewall if not r.get("disabled")
        )
        if has_input_rules and has_drop_invalid:
            scores["firewall"] = 15.0
            details["firewall"] = "Filter rules & invalid drops aktif"
        elif has_input_rules:
            scores["firewall"] = 12.0
            details["firewall"] = "Input rules aktif"
        else:
            scores["firewall"] = 7.0
            details["firewall"] = "Rules minimal atau default"
    elif firewall == []:
        scores["firewall"] = 5.0
        details["firewall"] = "Tidak ada filter rules (perhatian)"
    else:
        scores["firewall"] = 0.0
        details["firewall"] = "UNKNOWN"

    # 5. DNS (10%)
    if dns and isinstance(dns, dict):
        servers = dns.get("servers", []) + dns.get("dynamic_servers", [])
        allow_remote = dns.get("allow_remote_requests", False)
        if servers and not allow_remote:
            scores["dns"] = 10.0
            details["dns"] = f"DNS aktif ({len(servers)} servers, remote requests aman)"
        elif servers:
            scores["dns"] = 8.0
            details["dns"] = f"DNS aktif ({len(servers)} servers)"
        else:
            scores["dns"] = 4.0
            details["dns"] = "Server DNS kosong"
    else:
        scores["dns"] = 0.0
        details["dns"] = "UNKNOWN"

    # 6. DHCP (5%)
    if isinstance(dhcp, list):
        bound_count = sum(1 for d in dhcp if d.get("status") == "bound")
        scores["dhcp"] = 5.0
        details["dhcp"] = f"{bound_count} active leases"
    else:
        scores["dhcp"] = 0.0
        details["dhcp"] = "UNKNOWN"

    # 7. Resource Usage (10%) - RAM and HDD free space
    if system and isinstance(system, dict):
        mem_pct = system.get("memory", {}).get("usage_pct", 50)
        hdd_pct = system.get("hdd", {}).get("usage_pct", 50)
        if mem_pct < 75 and hdd_pct < 85:
            scores["resources"] = 10.0
            details["resources"] = f"RAM {mem_pct}%, Disk {hdd_pct}%"
        elif mem_pct < 90 and hdd_pct < 95:
            scores["resources"] = 6.0
            details["resources"] = f"RAM {mem_pct}%, Disk {hdd_pct}% (hampir penuh)"
        else:
            scores["resources"] = 2.0
            details["resources"] = f"RAM {mem_pct}%, Disk {hdd_pct}% (kritis)"
    else:
        scores["resources"] = 0.0
        details["resources"] = "UNKNOWN"

    total_score = round(sum(scores.values()))

    if total_score >= 90:
        status = "HEALTHY"
        status_emoji = "🟢"
    elif total_score >= 75:
        status = "GOOD"
        status_emoji = "🟡"
    elif total_score >= 60:
        status = "WARNING"
        status_emoji = "🟠"
    else:
        status = "CRITICAL"
        status_emoji = "🔴"

    return {
        "score": total_score,
        "status": status,
        "status_emoji": status_emoji,
        "category_scores": scores,
        "details": details,
    }
