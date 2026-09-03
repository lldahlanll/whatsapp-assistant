"""Network Security Audit Tool for MikroTik."""

from __future__ import annotations

from typing import Any

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient


async def security_audit(client: MikroTikRestClient) -> dict[str, Any]:
    """Perform a read-only security assessment of MikroTik router configuration.

    Analyzes:
    1. Management Service Exposure (/ip/service)
    2. Firewall Architecture & Rules (/ip/firewall/filter)
    3. DNS Resolver Exposure (/ip/dns)
    4. User Accounts & Management (/user)
    """
    findings: list[dict[str, Any]] = []
    base_score = 100

    # -------------------------------------------------------------
    # 1. Management Access Services
    # -------------------------------------------------------------
    try:
        raw_services = await client.get("ip/service")
        services = raw_services if isinstance(raw_services, list) else [raw_services]

        for svc in services:
            if not isinstance(svc, dict):
                continue
            name = svc.get("name", "").lower()
            disabled = svc.get("disabled") == "true" or svc.get("disabled") is True
            address = svc.get("address", "")
            port = svc.get("port")

            if not disabled:
                # Insecure legacy protocols
                if name == "telnet":
                    findings.append({
                        "title": "Telnet service is enabled",
                        "severity": "HIGH",
                        "evidence": f"Service: telnet, port: {port}, allowed address: '{address or 'unrestricted'}'",
                        "explanation": "Telnet transmits all data, including credentials, in unencrypted cleartext.",
                        "recommendation": "Disable telnet (`/ip service disable telnet`) and use SSH or TLS.",
                    })
                    base_score -= 15

                if name == "ftp":
                    findings.append({
                        "title": "FTP service is enabled",
                        "severity": "MEDIUM",
                        "evidence": f"Service: ftp, port: {port}, allowed address: '{address or 'unrestricted'}'",
                        "explanation": "FTP credentials and transferred files are sent in cleartext.",
                        "recommendation": "Disable FTP or restrict allowed address to trusted admin subnets.",
                    })
                    base_score -= 10

                # Unrestricted management interfaces
                if name in ("winbox", "ssh", "www", "api") and not address:
                    severity = "CRITICAL" if name in ("winbox", "api") else "HIGH"
                    penalty = 15 if severity == "CRITICAL" else 10
                    findings.append({
                        "title": f"Management service '{name}' is open to all IPs",
                        "severity": severity,
                        "evidence": f"Service: {name}, port: {port}, allowed address: (empty / 0.0.0.0/0)",
                        "explanation": (
                            f"The {name} interface accepts connections from any IP "
                            "if not restricted by firewall or address list."
                        ),
                        "recommendation": f"Set `address` whitelist on `/ip service set {name} address=<admin_ip>/32`.",
                    })
                    base_score -= penalty

    except Exception as exc:
        findings.append({
            "title": "Could not inspect IP services",
            "severity": "INFO",
            "evidence": str(exc),
            "explanation": "Service query endpoint was unavailable or restricted.",
            "recommendation": "Verify user permission has `read` policy on RouterOS.",
        })

    # -------------------------------------------------------------
    # 2. DNS Remote Requests (Open Resolver Check)
    # -------------------------------------------------------------
    try:
        raw_dns = await client.get("ip/dns")
        dns = raw_dns[0] if isinstance(raw_dns, list) and raw_dns else (
            raw_dns if isinstance(raw_dns, dict) else {}
        )
        allow_remote = (
            dns.get("allow-remote-requests") == "true" or dns.get("allow-remote-requests") is True
        )
        if allow_remote:
            findings.append({
                "title": "DNS Allow Remote Requests is enabled",
                "severity": "MEDIUM",
                "evidence": "allow-remote-requests: true",
                "explanation": "If port 53 is open on WAN input, router can be abused for DNS amplification attacks.",
                "recommendation": "Ensure WAN firewall drops port 53 or disable allow-remote-requests.",
            })
            base_score -= 10
    except Exception:
        pass

    # -------------------------------------------------------------
    # 3. Firewall Filter Rules Assessment
    # -------------------------------------------------------------
    try:
        raw_filters = await client.get("ip/firewall/filter")
        filters = raw_filters if isinstance(raw_filters, list) else [raw_filters]

        active_rules = [r for r in filters if isinstance(r, dict) and not (
            r.get("disabled") == "true" or r.get("disabled") is True
        )]

        input_drop_all = any(
            r.get("chain") == "input" and r.get("action") in ("drop", "reject")
            for r in active_rules
        )
        has_invalid_drop = any(
            r.get("action") == "drop" and "invalid" in str(r.get("comment", "")).lower()
            for r in active_rules
        )

        if not active_rules:
            findings.append({
                "title": "No active firewall filter rules found",
                "severity": "CRITICAL",
                "evidence": "Active filter rules: 0",
                "explanation": "Router is unprotected by stateful firewall filter rules.",
                "recommendation": "Configure standard input and forward filter rules immediately.",
            })
            base_score -= 30
        elif not input_drop_all:
            findings.append({
                "title": "Missing default drop rule on input chain",
                "severity": "HIGH",
                "evidence": "Input chain has no final drop/reject rule",
                "explanation": "Unmatched packets are implicitly accepted by RouterOS default policy.",
                "recommendation": "Add a final drop rule on chain=input for unwanted incoming traffic.",
            })
            base_score -= 15

        if active_rules and not has_invalid_drop:
            findings.append({
                "title": "Invalid connection drop rule missing",
                "severity": "LOW",
                "evidence": "No drop rule with connection-state=invalid found",
                "explanation": "Dropping invalid packets prevents state table exhaustion attacks.",
                "recommendation": (
                    "Add rule: `/ip firewall filter add chain=input "
                    "connection-state=invalid action=drop`."
                ),
            })
            base_score -= 5


    except Exception:
        pass

    # -------------------------------------------------------------
    # 4. User Accounts Check
    # -------------------------------------------------------------
    try:
        raw_users = await client.get("user")
        users = raw_users if isinstance(raw_users, list) else [raw_users]

        for u in users:
            if not isinstance(u, dict):
                continue
            name = u.get("name", "")
            disabled = u.get("disabled") == "true" or u.get("disabled") is True
            group = u.get("group", "")

            if name.lower() == "admin" and not disabled and group == "full":
                findings.append({
                    "title": "Default 'admin' account is active",
                    "severity": "MEDIUM",
                    "evidence": "User 'admin' with 'full' group is enabled",
                    "explanation": "Automated brute-force bots target the default 'admin' username first.",
                    "recommendation": "Create a unique admin username and disable or delete 'admin'.",
                })
                base_score -= 10
    except Exception:
        pass


    final_score = max(0, min(100, base_score))

    # Determine audit severity summary
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    highest_severity = "CLEAN"
    for sev in severity_order:
        if any(f["severity"] == sev for f in findings):
            highest_severity = sev
            break

    return {
        "security_score": final_score,
        "highest_severity": highest_severity,
        "total_findings": len(findings),
        "findings": findings,
    }
