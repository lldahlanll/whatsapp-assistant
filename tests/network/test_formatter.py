"""Unit tests for WhatsApp message formatters."""

from whatsapp_platform.features.network.formatter import (
    format_health_report,
    format_network_error,
)
from whatsapp_platform.infrastructure.mikrotik.exceptions import (
    MikroTikAuthError,
    MikroTikDisabledError,
    MikroTikTimeoutError,
)


def test_format_health_report() -> None:
    report = {
        "system": {
            "board_name": "hAP ac2",
            "version": "7.15",
            "uptime": "2d 4h",
            "cpu_load": 10,
            "memory": {"usage_pct": 45.0, "total_bytes": 1048576, "free_bytes": 524288},
            "temperature": 42.0,
        },
        "health_score": {
            "score": 95,
            "status": "HEALTHY",
            "status_emoji": "🟢",
        },
        "running_interfaces": 3,
        "interfaces_count": 5,
        "active_dhcp_count": 8,
    }
    output = format_health_report(report)
    assert "hAP ac2" in output
    assert "95/100" in output
    assert "42.0°C" in output


def test_format_network_error_types() -> None:
    assert "nonaktif" in format_network_error(MikroTikDisabledError()).lower()
    assert "autentikasi" in format_network_error(MikroTikAuthError()).lower()
    assert "timeout" in format_network_error(MikroTikTimeoutError()).lower()
