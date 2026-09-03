"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness(api_client: AsyncClient) -> None:
    """GET /health returns 200 with running status."""
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "running" in data["message"].lower()


@pytest.mark.asyncio
async def test_health_readiness(api_client: AsyncClient) -> None:
    """GET /health/ready returns 200 when container is available."""
    response = await api_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_health_process_time_header(api_client: AsyncClient) -> None:
    """Response includes X-Process-Time header."""
    response = await api_client.get("/health")
    assert "x-process-time" in response.headers
