"""Unit tests for individual MikroTik read-only tools."""

from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient
from whatsapp_platform.infrastructure.mikrotik.tools.connections import get_active_connections
from whatsapp_platform.infrastructure.mikrotik.tools.dhcp import get_dhcp_leases
from whatsapp_platform.infrastructure.mikrotik.tools.dns import get_dns_status
from whatsapp_platform.infrastructure.mikrotik.tools.firewall import get_firewall_rules, get_nat_rules
from whatsapp_platform.infrastructure.mikrotik.tools.interfaces import get_interfaces
from whatsapp_platform.infrastructure.mikrotik.tools.logs import get_logs
from whatsapp_platform.infrastructure.mikrotik.tools.system import get_system_health


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=MikroTikRestClient)
    return client


@pytest.mark.asyncio
async def test_get_system_health(mock_client: AsyncMock) -> None:
    mock_client.get.side_effect = lambda endpoint: {
        "system/resource": [{
            "version": "7.16",
            "board-name": "hAP ax3",
            "cpu-load": "12",
            "total-memory": "1048576",
            "free-memory": "524288",
        }],
        "system/health": [{"name": "temperature", "value": "45"}],
        "system/routerboard": [{"model": "C53UiG+5HPaxD2HPaxD"}],
    }.get(endpoint, [])

    result = await get_system_health(mock_client)
    assert result["version"] == "7.16"
    assert result["board_name"] == "C53UiG+5HPaxD2HPaxD"
    assert result["cpu_load"] == 12
    assert result["temperature"] == 45.0
    assert result["memory"]["usage_pct"] == 50.0


@pytest.mark.asyncio
async def test_get_interfaces(mock_client: AsyncMock) -> None:
    mock_client.get.return_value = [
        {
            "name": "ether1",
            "type": "ether",
            "running": "true",
            "disabled": "false",
            "rx-byte": "1000",
            "tx-byte": "2000",
            "rx-error": "0",
            "tx-error": "0",
        }
    ]

    result = await get_interfaces(mock_client)
    assert len(result) == 1
    assert result[0]["name"] == "ether1"
    assert result[0]["running"] is True
    assert result[0]["traffic"]["rx_bytes"] == 1000


@pytest.mark.asyncio
async def test_get_dhcp_leases(mock_client: AsyncMock) -> None:
    mock_client.get.return_value = [
        {"address": "192.168.88.10", "mac-address": "AA:BB:CC:DD:EE:01", "host-name": "Laptop", "status": "bound"},
        {"address": "192.168.88.20", "mac-address": "AA:BB:CC:DD:EE:02", "host-name": "Phone", "status": "bound"},
    ]

    all_leases = await get_dhcp_leases(mock_client)
    assert len(all_leases) == 2

    filtered = await get_dhcp_leases(mock_client, filter_query="Laptop")
    assert len(filtered) == 1
    assert filtered[0]["address"] == "192.168.88.10"


@pytest.mark.asyncio
async def test_get_active_connections(mock_client: AsyncMock) -> None:
    mock_client.get.return_value = [
        {"protocol": "tcp", "src-address": "192.168.88.10:5000", "dst-address": "1.1.1.1:443"},
        {"protocol": "tcp", "src-address": "192.168.88.10:5001", "dst-address": "8.8.8.8:53"},
        {"protocol": "udp", "src-address": "192.168.88.20:1234", "dst-address": "8.8.4.4:53"},
    ]

    result = await get_active_connections(mock_client)
    assert result["total_connections"] == 3
    assert result["protocol_distribution"]["tcp"] == 2
    assert result["top_sources"][0]["ip"] == "192.168.88.10"


@pytest.mark.asyncio
async def test_get_firewall_and_nat(mock_client: AsyncMock) -> None:
    mock_client.get.side_effect = lambda endpoint: {
        "ip/firewall/filter": [
            {"chain": "input", "action": "accept", "comment": "defconf: accept established,related"}
        ],
        "ip/firewall/nat": [{"chain": "srcnat", "action": "masquerade", "out-interface": "ether1"}],
    }.get(endpoint, [])

    filters = await get_firewall_rules(mock_client)
    nats = await get_nat_rules(mock_client)
    assert len(filters) == 1
    assert filters[0]["chain"] == "input"
    assert len(nats) == 1
    assert nats[0]["action"] == "masquerade"


@pytest.mark.asyncio
async def test_get_dns_status(mock_client: AsyncMock) -> None:
    mock_client.get.return_value = [
        {"servers": "1.1.1.1,8.8.8.8", "allow-remote-requests": "true", "cache-size": "2048"}
    ]

    result = await get_dns_status(mock_client)
    assert result["servers"] == ["1.1.1.1", "8.8.8.8"]
    assert result["allow_remote_requests"] is True



@pytest.mark.asyncio
async def test_get_logs(mock_client: AsyncMock) -> None:
    mock_client.get.return_value = [
        {"time": "10:00:00", "topics": "system,info", "message": "router rebooted"},
        {"time": "10:01:00", "topics": "dhcp,warning", "message": "dhcp lease expired"},
    ]

    logs = await get_logs(mock_client, limit=5)
    assert len(logs) == 2
    assert logs[0]["topics"] == "dhcp,warning"  # Newest first
