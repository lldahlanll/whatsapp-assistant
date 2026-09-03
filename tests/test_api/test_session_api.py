"""Tests for session API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_session_status_no_session(api_client: AsyncClient) -> None:
    """GET /api/v1/session returns INITIALIZING when no session record exists."""
    response = await api_client.get("/api/v1/session")
    assert response.status_code == 200
    data = response.json()
    assert data["session_name"] == "test-session"
    assert data["is_connected"] is False
    assert data["status"] == "INITIALIZING"


@pytest.mark.asyncio
async def test_disconnect_session(api_client: AsyncClient) -> None:
    """POST /api/v1/session/disconnect returns success."""
    response = await api_client.post("/api/v1/session/disconnect")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "disconnected" in data["message"].lower()


@pytest.mark.asyncio
async def test_session_requires_api_key_when_configured(api_client_with_key: AsyncClient) -> None:
    """GET /api/v1/session returns 401 without API key when auth is enabled."""
    response = await api_client_with_key.get("/api/v1/session")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_accepts_valid_api_key(api_client_with_key: AsyncClient) -> None:
    """GET /api/v1/session returns 200 with correct API key."""
    response = await api_client_with_key.get(
        "/api/v1/session",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
