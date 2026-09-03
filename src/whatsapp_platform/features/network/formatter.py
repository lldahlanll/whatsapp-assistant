"""WhatsApp message formatters for Network AI responses."""

from __future__ import annotations

from typing import Any


def _format_bytes(bytes_count: int) -> str:
    """Format bytes into readable human unit (KB, MB, GB)."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def format_health_report(report: dict[str, Any]) -> str:
    """Format network health report for WhatsApp."""
    system = report.get("system", {})
    health_score = report.get("health_score", {})
    score = health_score.get("score", 0)
    status_emoji = health_score.get("status_emoji", "🟢")
    status = health_score.get("status", "HEALTHY")

    board = system.get("board_name", "MikroTik")
    version = system.get("version", "v7")
    uptime = system.get("uptime", "-")
    cpu = system.get("cpu_load", 0)
    mem_pct = system.get("memory", {}).get("usage_pct", 0)
    total_mem = _format_bytes(system.get("memory", {}).get("total_bytes", 0))
    free_mem = _format_bytes(system.get("memory", {}).get("free_bytes", 0))

    temp_str = f"\n🌡️ *Suhu*: {system.get('temperature')}°C" if system.get("temperature") is not None else ""

    running_ifaces = report.get("running_interfaces", 0)
    total_ifaces = report.get("interfaces_count", 0)
    active_dhcp = report.get("active_dhcp_count", 0)

    summary_note = (
        "Tidak ditemukan masalah kritis."
        if score >= 85
        else "Ditemukan beberapa indikator yang perlu diperhatikan."
    )

    return (
        f"📡 *Kondisi Jaringan MikroTik*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status_emoji} *{status}* (Skor: *{score}/100*)\n\n"
        f"📟 *Perangkat*: `{board}` (RouterOS `{version}`)\n"
        f"⏱️ *Uptime*: {uptime}\n"
        f"⚙️ *CPU Load*: {cpu}%\n"
        f"🧠 *RAM*: {mem_pct}% (Free: {free_mem} / {total_mem}){temp_str}\n"
        f"🔌 *Interface*: {running_ifaces}/{total_ifaces} Aktif\n"
        f"👥 *DHCP Client*: {active_dhcp} perangkat\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ℹ️ _{summary_note}_"
    )


def format_traffic_report(report: dict[str, Any]) -> str:
    """Format interface traffic report for WhatsApp."""
    interfaces = report.get("interfaces", [])
    if not interfaces:
        return "📊 *Traffic Interface*\n\nTidak ada interface aktif yang ditemukan."

    lines = ["📊 *Traffic & Bandwidth Interface*", "━━━━━━━━━━━━━━━━━━"]
    for iface in interfaces:
        name = iface.get("name", "unknown")
        running = "🟢 UP" if iface.get("running") else "🔴 DOWN"
        traffic = iface.get("traffic", {})
        rx = _format_bytes(traffic.get("rx_bytes", 0))
        tx = _format_bytes(traffic.get("tx_bytes", 0))
        health = iface.get("health", {})
        errors = health.get("rx_errors", 0) + health.get("tx_errors", 0)
        drops = health.get("rx_drops", 0) + health.get("tx_drops", 0)

        err_str = f" | ⚠️ Err/Drop: {errors}/{drops}" if (errors > 0 or drops > 0) else ""

        lines.append(
            f"• *{name}* ({running})\n"
            f"  📥 RX: `{rx}` | 📤 TX: `{tx}`{err_str}"
        )

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("ℹ️ _Data traffic dihitung secara kumulatif._")
    return "\n".join(lines)


def format_security_report(report: dict[str, Any]) -> str:
    """Format security audit report for WhatsApp."""
    score = report.get("security_score", 100)
    highest = report.get("highest_severity", "CLEAN")
    findings = report.get("findings", [])

    status_emoji = "🟢" if score >= 85 else ("🟡" if score >= 70 else "🔴")

    lines = [
        "🛡️ *Audit Keamanan MikroTik*",
        "━━━━━━━━━━━━━━━━━━",
        f"Skor Keamanan: {status_emoji} *{score}/100*",
        f"Tingkat Risiko: *{highest}*",
        f"Temuan: *{len(findings)} isu*",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if not findings:
        lines.append("✅ *Konfigurasi router dalam kondisi aman dan terlindungi.*")
    else:
        for idx, f in enumerate(findings[:5], start=1):
            sev = f.get("severity", "INFO")
            sev_icon = "🚨" if sev == "CRITICAL" else ("⚠️" if sev in ("HIGH", "MEDIUM") else "ℹ️")
            lines.append(
                f"{idx}. {sev_icon} *[{sev}]* {f.get('title')}\n"
                f"   _Bukti_: `{f.get('evidence')}`\n"
                f"   💡 _Saran_: {f.get('recommendation')}\n"
            )

        if len(findings) > 5:
            lines.append(f"_...dan {len(findings) - 5} temuan lainnya._")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("🔒 _Audit bersifat Read-Only tanpa mengubah konfigurasi._")
    return "\n".join(lines)


def format_dhcp_report(leases: list[dict[str, Any]]) -> str:
    """Format DHCP leases for WhatsApp."""
    if not leases:
        return "👥 *Daftar DHCP Leases*\n\nTidak ada client DHCP aktif yang terdaftar."

    lines = [
        "👥 *Daftar DHCP Leases (Client Aktif)*",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for item in leases[:15]:
        ip = item.get("address", "-")
        host = item.get("hostname") or item.get("comment") or "Unknown Device"
        mac = item.get("mac_address", "-")
        status = "🟢" if item.get("status") == "bound" else "⚪"
        lines.append(f"{status} *{ip}* — {host}\n   └ MAC: `{mac}`")

    if len(leases) > 15:
        lines.append(f"\n_...total {len(leases)} perangkat terhubung._")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_firewall_report(report: dict[str, Any]) -> str:
    """Format firewall & NAT report for WhatsApp."""
    filters = report.get("filter_rules", [])
    nats = report.get("nat_rules", [])

    lines = [
        "🧱 *Ringkasan Firewall & NAT*",
        "━━━━━━━━━━━━━━━━━━",
        f"• Total Filter Rules: *{len(filters)}*",
        f"• Total NAT Rules: *{len(nats)}*",
        "\n📋 *Filter Rules Utama*:",
    ]

    active_filters = [f for f in filters if not f.get("disabled")][:5]
    if active_filters:
        for f in active_filters:
            chain = f.get("chain", "forward")
            action = f.get("action", "accept")
            comment = f" ({f.get('comment')})" if f.get("comment") else ""
            lines.append(f"  • `{chain}` ➔ *{action.upper()}*{comment}")
    else:
        lines.append("  _Tidak ada filter rule aktif._")

    lines.append("\n🔄 *NAT Rules*:")
    active_nats = [n for n in nats if not n.get("disabled")][:3]
    if active_nats:
        for n in active_nats:
            chain = n.get("chain", "srcnat")
            action = n.get("action", "masquerade")
            comment = f" ({n.get('comment')})" if n.get("comment") else ""
            lines.append(f"  • `{chain}` ➔ *{action.upper()}*{comment}")
    else:
        lines.append("  _Tidak ada NAT rule aktif._")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_logs_report(logs: list[dict[str, Any]]) -> str:
    """Format router logs for WhatsApp."""
    if not logs:
        return "📜 *Log Aktivitas Router*\n\nTidak ada catatan log terbaru."

    lines = [
        "📜 *Log Aktivitas Router Terbaru*",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for log in logs[:10]:
        time_str = log.get("time", "")
        topics = log.get("topics", "system")
        msg = log.get("message", "")
        lines.append(f"• `[{time_str}]` *{topics}*:\n  {msg}")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_network_error(exc: Exception) -> str:
    """Format user-friendly error message for network/router issues."""
    from whatsapp_platform.infrastructure.mikrotik.exceptions import (
        MikroTikAuthError,
        MikroTikDisabledError,
        MikroTikPermissionError,
        MikroTikTimeoutError,
    )

    if isinstance(exc, MikroTikDisabledError):
        return (
            "⚠️ *Fitur MikroTik Belum Diaktifkan*\n\n"
            "Integrasi MikroTik saat ini sedang nonaktif di konfigurasi bot."
        )

    if isinstance(exc, MikroTikAuthError):
        return (
            "⚠️ *Gagal Terhubung ke MikroTik*\n\n"
            "Status: Autentikasi atau izin akses RouterOS ditolak.\n"
            "Periksa username dan password akun API MikroTik Anda."
        )

    if isinstance(exc, MikroTikTimeoutError):
        return (
            "⚠️ *Koneksi MikroTik Timeout*\n\n"
            "Status: Router tidak merespons dalam batas waktu yang ditentukan.\n"
            "Periksa apakah service `www` / `www-ssl` aktif dan router dapat dijangkau."
        )

    if isinstance(exc, MikroTikPermissionError):
        return (
            "⛔ *Akses Ditolak*\n\n"
            "Nomor atau grup WhatsApp Anda tidak memiliki izin untuk menjalankan Network AI."
        )

    return (
        "⚠️ *Maaf, tidak dapat mengambil data dari MikroTik saat ini.*\n\n"
        "Status: Gangguan koneksi jaringan ke router.\n"
        "_(Tidak ada perubahan konfigurasi apa pun yang dilakukan)_"
    )
