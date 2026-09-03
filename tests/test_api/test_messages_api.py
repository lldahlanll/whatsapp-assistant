"""Tests for messages API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_send_message_success(api_client: AsyncClient) -> None:
    """POST /api/v1/messages/send returns 201 with message response."""
    response = await api_client.post(
        "/api/v1/messages/send",
        json={"to": "628123456789@s.whatsapp.net", "text": "Hello from test!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["chat_jid"] == "628123456789@s.whatsapp.net"
    assert data["text"] == "Hello from test!"
    assert data["direction"] == "OUTBOUND"
    assert data["is_from_me"] is True
    assert data["status"] == "SENT"
    assert "id" in data


@pytest.mark.asyncio
async def test_send_message_invalid_jid(api_client: AsyncClient) -> None:
    """POST /api/v1/messages/send returns 422 for invalid JID."""
    response = await api_client.post(
        "/api/v1/messages/send",
        json={"to": "not-a-valid-jid", "text": "Hello"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_message_empty_text(api_client: AsyncClient) -> None:
    """POST /api/v1/messages/send returns 422 for empty text."""
    response = await api_client.post(
        "/api/v1/messages/send",
        json={"to": "628123456789@s.whatsapp.net", "text": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_message_missing_fields(api_client: AsyncClient) -> None:
    """POST /api/v1/messages/send returns 422 for missing required fields."""
    response = await api_client.post("/api/v1/messages/send", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_conversation_history_empty(api_client: AsyncClient) -> None:
    """GET /api/v1/messages/{jid}/history returns empty list when no messages."""
    response = await api_client.get(
        "/api/v1/messages/628123456789@s.whatsapp.net/history"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["chat_jid"] == "628123456789@s.whatsapp.net"
    assert data["messages"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_conversation_history_after_send(api_client: AsyncClient) -> None:
    """GET history returns sent messages stored in DB."""
    jid = "628999888777@s.whatsapp.net"

    # Send a message first
    send_resp = await api_client.post(
        "/api/v1/messages/send",
        json={"to": jid, "text": "Stored message"},
    )
    assert send_resp.status_code == 201

    # Then retrieve history
    history_resp = await api_client.get(f"/api/v1/messages/{jid}/history")
    assert history_resp.status_code == 200
    data = history_resp.json()
    assert data["total"] >= 1
    assert any(m["text"] == "Stored message" for m in data["messages"])


@pytest.mark.asyncio
async def test_get_conversation_history_pagination(api_client: AsyncClient) -> None:
    """GET history respects limit and offset query params."""
    response = await api_client.get(
        "/api/v1/messages/628123456789@s.whatsapp.net/history",
        params={"limit": 10, "offset": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
