"""Unit tests for MikroTik Tool Executor and Tool Schemas."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.infrastructure.mikrotik.tool_executor import MikroTikToolExecutor
from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS


def test_tool_definitions_and_schema_conversion() -> None:
    """Verify tool schema definitions convert properly to OpenAI and Gemini formats."""
    assert len(MIKROTIK_TOOLS) >= 7

    traffic_tool = next(t for t in MIKROTIK_TOOLS if t.name == "mikrotik_get_traffic")
    openai_schema = traffic_tool.to_openai_schema()
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "mikrotik_get_traffic"
    assert "interface_name" in openai_schema["function"]["parameters"]["properties"]

    gemini_schema = traffic_tool.to_gemini_schema()
    assert gemini_schema["name"] == "mikrotik_get_traffic"
    assert "interface_name" in gemini_schema["parameters"]["properties"]
    assert gemini_schema["parameters"]["properties"]["interface_name"]["type"] == "STRING"


@pytest.mark.asyncio
async def test_tool_executor_permission_denied() -> None:
    """Verify executor rejects unauthorized callers."""
    toolbox = MagicMock()
    perm_checker = MagicMock()
    perm_checker.has_network_read_permission.return_value = False

    executor = MikroTikToolExecutor(toolbox, perm_checker)
    user_jid = JID.parse("628123456789@s.whatsapp.net")
    chat_jid = JID.parse("628123456789@s.whatsapp.net")

    res_raw = await executor.execute("mikrotik_get_health", {}, user_jid, chat_jid)
    res = json.loads(res_raw)
    assert res["status"] == "error"
    assert "Izin ditolak" in res["error"]
    toolbox.get_health_report.assert_not_called()


@pytest.mark.asyncio
async def test_tool_executor_disabled_guard() -> None:
    """Verify executor returns error when MikroTik is disabled."""
    toolbox = MagicMock()
    toolbox.is_enabled = False
    perm_checker = MagicMock()
    perm_checker.has_network_read_permission.return_value = True

    executor = MikroTikToolExecutor(toolbox, perm_checker)
    user_jid = JID.parse("628123456789@s.whatsapp.net")
    chat_jid = JID.parse("628123456789@s.whatsapp.net")

    res_raw = await executor.execute("mikrotik_get_health", {}, user_jid, chat_jid)
    res = json.loads(res_raw)
    assert res["status"] == "error"
    assert "dinonaktifkan" in res["error"]


@pytest.mark.asyncio
async def test_tool_executor_successful_execution() -> None:
    """Verify executor dispatches to appropriate toolbox methods."""
    toolbox = MagicMock()
    toolbox.is_enabled = True
    toolbox.get_health_report = AsyncMock(return_value={"cpu_load": 15, "board_name": "hAP ax2"})
    toolbox.get_traffic_report = AsyncMock(return_value={"rx_bps": 1000000, "tx_bps": 500000})
    toolbox.get_dhcp_report = AsyncMock(return_value=[{"address": "192.168.1.50", "host_name": "iPhone"}])

    perm_checker = MagicMock()
    perm_checker.has_network_read_permission.return_value = True

    executor = MikroTikToolExecutor(toolbox, perm_checker)
    user_jid = JID.parse("628123456789@s.whatsapp.net")
    chat_jid = JID.parse("628123456789@s.whatsapp.net")

    # 1. Health tool
    health_raw = await executor.execute("mikrotik_get_health", {}, user_jid, chat_jid)
    health_res = json.loads(health_raw)
    assert health_res["status"] == "success"
    assert health_res["data"]["board_name"] == "hAP ax2"

    # 2. Traffic tool
    traffic_raw = await executor.execute("mikrotik_get_traffic", {"interface_name": "ether1"}, user_jid, chat_jid)
    traffic_res = json.loads(traffic_raw)
    assert traffic_res["status"] == "success"
    assert traffic_res["data"]["rx_bps"] == 1000000

    # 3. Unknown tool
    unknown_raw = await executor.execute("mikrotik_unknown_cmd", {}, user_jid, chat_jid)
    unknown_res = json.loads(unknown_raw)
    assert unknown_res["status"] == "error"
