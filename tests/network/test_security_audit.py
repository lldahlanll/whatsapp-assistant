"""Unit tests for Security Audit tool."""

from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient
from whatsapp_platform.infrastructure.mikrotik.tools.security import security_audit


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock(spec=MikroTikRestClient)


@pytest.mark.asyncio
async def test_security_audit_detects_telnet_and_open_services(mock_client: AsyncMock) -> None:
    mock_client.get.side_effect = lambda endpoint: {
        "ip/service": [
            {"name": "telnet", "port": 23, "disabled": "false", "address": ""},
            {"name": "winbox", "port": 8291, "disabled": "false", "address": ""},
            {"name": "ssh", "port": 22, "disabled": "false", "address": "192.168.88.0/24"},
        ],
        "ip/dns": [{"allow-remote-requests": "true"}],
        "ip/firewall/filter": [
            {"chain": "input", "action": "accept", "disabled": False},
        ],
        "user": [
            {"name": "admin", "disabled": False, "group": "full"},
        ],
    }.get(endpoint, [])

    report = await security_audit(mock_client)
    assert report["total_findings"] >= 4
    assert any(f["title"] == "Telnet service is enabled" for f in report["findings"])
    assert any("winbox" in f["title"] for f in report["findings"])
    assert any("admin" in f["title"] for f in report["findings"])
    assert report["security_score"] < 70
    assert report["highest_severity"] in ("CRITICAL", "HIGH")
