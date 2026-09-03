"""Unit tests for Network Health Score calculation."""

from whatsapp_platform.infrastructure.mikrotik.tools.health_score import calculate_health_score


def test_calculate_health_score_healthy() -> None:
    metrics = {
        "system": {
            "cpu_load": 15,
            "memory": {"usage_pct": 35.0},
            "hdd": {"usage_pct": 40.0},
        },
        "interfaces": [
            {
                "name": "ether1-WAN",
                "running": True,
                "health": {"rx_errors": 0, "tx_errors": 0, "rx_drops": 0, "tx_drops": 0},
            }
        ],
        "firewall": [
            {"chain": "input", "action": "accept", "disabled": False},
            {"chain": "input", "action": "drop", "comment": "drop invalid", "disabled": False},
        ],
        "dns": {
            "servers": ["1.1.1.1"],
            "allow_remote_requests": False,
        },
        "dhcp": [
            {"status": "bound"},
            {"status": "bound"},
        ],
    }

    result = calculate_health_score(metrics)
    assert result["score"] >= 90
    assert result["status"] == "HEALTHY"
    assert result["status_emoji"] == "🟢"


def test_calculate_health_score_critical_when_empty() -> None:
    result = calculate_health_score({})
    assert result["score"] < 60
    assert result["status"] == "CRITICAL"
    assert result["status_emoji"] == "🔴"
    assert result["details"]["system"] == "UNKNOWN"
