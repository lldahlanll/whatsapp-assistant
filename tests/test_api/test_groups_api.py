"""Tests for group management API endpoints."""

import pytest
from httpx import AsyncClient

GROUP_JID = "120363000123456789@g.us"
MEMBER_JID = "628123456789@s.whatsapp.net"


@pytest.mark.asyncio
async def test_get_group_info(api_client: AsyncClient) -> None:
    """GET /api/v1/groups/{jid} returns group info from mock gateway."""
    response = await api_client.get(f"/api/v1/groups/{GROUP_JID}")
    assert response.status_code == 200
    data = response.json()
    assert data["jid"] == GROUP_JID
    assert "name" in data
    assert "participants" in data


@pytest.mark.asyncio
async def test_get_group_info_invalid_jid(api_client: AsyncClient) -> None:
    """GET /api/v1/groups/{jid} returns 422 for non-group JID."""
    response = await api_client.get("/api/v1/groups/628123456789@s.whatsapp.net")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_invite_link(api_client: AsyncClient) -> None:
    """GET /api/v1/groups/{jid}/invite returns invite link."""
    response = await api_client.get(f"/api/v1/groups/{GROUP_JID}/invite")
    assert response.status_code == 200
    data = response.json()
    assert data["jid"] == GROUP_JID
    assert data["invite_link"].startswith("https://chat.whatsapp.com/")


@pytest.mark.asyncio
async def test_add_member(api_client: AsyncClient) -> None:
    """POST /api/v1/groups/{jid}/members adds member successfully."""
    response = await api_client.post(
        f"/api/v1/groups/{GROUP_JID}/members",
        json={"member_jid": MEMBER_JID},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_add_member_invalid_jid(api_client: AsyncClient) -> None:
    """POST /api/v1/groups/{jid}/members returns 422 for invalid member JID."""
    response = await api_client.post(
        f"/api/v1/groups/{GROUP_JID}/members",
        json={"member_jid": "not-valid"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_kick_member(api_client: AsyncClient) -> None:
    """DELETE /api/v1/groups/{jid}/members/{member_jid} kicks member."""
    response = await api_client.delete(
        f"/api/v1/groups/{GROUP_JID}/members/{MEMBER_JID}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_promote_member(api_client: AsyncClient) -> None:
    """POST promote endpoint returns success."""
    response = await api_client.post(
        f"/api/v1/groups/{GROUP_JID}/members/{MEMBER_JID}/promote"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_demote_member(api_client: AsyncClient) -> None:
    """POST demote endpoint returns success."""
    response = await api_client.post(
        f"/api/v1/groups/{GROUP_JID}/members/{MEMBER_JID}/demote"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_rename_group(api_client: AsyncClient) -> None:
    """PUT /api/v1/groups/{jid}/name renames group."""
    response = await api_client.put(
        f"/api/v1/groups/{GROUP_JID}/name",
        json={"name": "New Group Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "New Group Name" in data["message"]


@pytest.mark.asyncio
async def test_rename_group_empty_name(api_client: AsyncClient) -> None:
    """PUT /api/v1/groups/{jid}/name returns 422 for empty name."""
    response = await api_client.put(
        f"/api/v1/groups/{GROUP_JID}/name",
        json={"name": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_leave_group(api_client: AsyncClient) -> None:
    """POST /api/v1/groups/{jid}/leave leaves group."""
    response = await api_client.post(f"/api/v1/groups/{GROUP_JID}/leave")
    assert response.status_code == 200
    assert response.json()["success"] is True
