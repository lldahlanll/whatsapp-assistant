from unittest.mock import AsyncMock

import httpx
import pytest

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.mikrotik.client import MikroTikRestClient
from whatsapp_platform.infrastructure.mikrotik.exceptions import (
    MikroTikAuthError,
    MikroTikConnectionError,
    MikroTikDisabledError,
    MikroTikTimeoutError,
)


@pytest.fixture
def enabled_settings() -> Settings:
    return Settings(
        mikrotik_enabled=True,
        mikrotik_host="192.168.88.1",
        mikrotik_port=80,
        mikrotik_username="admin",
        mikrotik_password="password",
        mikrotik_use_ssl=False,
        mikrotik_timeout=2.0,
    )


@pytest.mark.asyncio
async def test_client_disabled_raises_error() -> None:
    settings = Settings(mikrotik_enabled=False)
    client = MikroTikRestClient(settings)
    with pytest.raises(MikroTikDisabledError):
        await client.get("system/resource")


@pytest.mark.asyncio
async def test_client_get_success(enabled_settings: Settings) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json.return_value = {"version": "7.15.2", "cpu-load": "15"}

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.return_value = mock_response

    client = MikroTikRestClient(enabled_settings, http_client=mock_http_client)
    result = await client.get("system/resource")
    assert isinstance(result, dict)
    assert result["version"] == "7.15.2"
    assert result["cpu-load"] == "15"


@pytest.mark.asyncio
async def test_client_auth_error_401(enabled_settings: Settings) -> None:
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.is_error = True

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.return_value = mock_response

    client = MikroTikRestClient(enabled_settings, http_client=mock_http_client)
    with pytest.raises(MikroTikAuthError):
        await client.get("system/resource")


@pytest.mark.asyncio
async def test_client_timeout_error(enabled_settings: Settings) -> None:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.side_effect = httpx.TimeoutException("Timeout")

    client = MikroTikRestClient(enabled_settings, http_client=mock_http_client)
    with pytest.raises(MikroTikTimeoutError):
        await client.get("system/resource")


@pytest.mark.asyncio
async def test_client_connection_error(enabled_settings: Settings) -> None:
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")

    client = MikroTikRestClient(enabled_settings, http_client=mock_http_client)
    with pytest.raises(MikroTikConnectionError):
        await client.get("system/resource")

