"""Groups management router.

Endpoints:
- GET    /api/v1/groups/{group_jid}                        — Get group info
- GET    /api/v1/groups/{group_jid}/invite                 — Get invite link
- POST   /api/v1/groups/{group_jid}/members                — Add member
- DELETE /api/v1/groups/{group_jid}/members/{member_jid}   — Kick member
- POST   /api/v1/groups/{group_jid}/members/{member_jid}/promote — Promote to admin
- POST   /api/v1/groups/{group_jid}/members/{member_jid}/demote  — Demote from admin
- PUT    /api/v1/groups/{group_jid}/name                   — Rename group
- POST   /api/v1/groups/{group_jid}/leave                  — Leave group
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.domain.exceptions.exceptions import GatewayException, InvalidJIDError
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.presentation.api.dependencies import get_manage_group_uc, verify_api_key
from whatsapp_platform.presentation.api.schemas.common_schemas import SuccessResponse
from whatsapp_platform.presentation.api.schemas.group_schemas import (
    GroupInfoResponse,
    GroupInviteResponse,
    GroupMemberRequest,
    GroupParticipantInfo,
    GroupRenameRequest,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/groups",
    tags=["Groups"],
    dependencies=[Depends(verify_api_key)],
)


def _parse_group_jid(group_jid: str) -> JID:
    """Parse and validate group JID, raising 422 on invalid format."""
    try:
        jid = JID.parse(group_jid)
        if not jid.is_group:
            raise ValueError("JID is not a group JID (must end with @g.us)")
        return jid
    except (ValueError, InvalidJIDError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid group JID: {exc}",
        ) from exc


def _parse_jid(jid_str: str) -> JID:
    """Parse any JID, raising 422 on invalid format."""
    try:
        return JID.parse(jid_str)
    except (ValueError, InvalidJIDError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid JID: {exc}",
        ) from exc


def _map_gateway_exc(exc: GatewayException) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"WhatsApp gateway error: {exc}",
    )


@router.get(
    "/{group_jid}",
    response_model=GroupInfoResponse,
    summary="Get group info",
    description="Retrieve info for a WhatsApp group by its JID (URL-encoded).",
)
async def get_group_info(
    group_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> GroupInfoResponse:
    jid = _parse_group_jid(group_jid)
    try:
        info: dict = await manage_group_uc.get_group_info(jid)
        raw_participants = info.get("participants", [])
        participants = [
            GroupParticipantInfo(
                jid=p if isinstance(p, str) else str(p.get("jid", "")),
                is_admin=False if isinstance(p, str) else p.get("is_admin", False),
                is_super_admin=False if isinstance(p, str) else p.get("is_super_admin", False),
            )
            for p in raw_participants
        ]
        return GroupInfoResponse(
            jid=group_jid,
            name=info.get("name", ""),
            description=info.get("description", ""),
            participant_count=len(participants),
            participants=participants,
            is_announce=info.get("is_announce", False),
            is_locked=info.get("is_locked", False),
        )
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to get group info", group_jid=group_jid, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get group info"
        ) from exc


@router.get(
    "/{group_jid}/invite",
    response_model=GroupInviteResponse,
    summary="Get group invite link",
    description="Retrieve the invite link for a group. Optionally revoke and regenerate.",
)
async def get_invite_link(
    group_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
    revoke: bool = Query(default=False, description="If true, revoke current link and generate new one"),
) -> GroupInviteResponse:
    jid = _parse_group_jid(group_jid)
    try:
        link = await manage_group_uc.get_invite_link(jid, revoke=revoke)
        return GroupInviteResponse(jid=group_jid, invite_link=link)
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to get invite link", group_jid=group_jid, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get invite link"
        ) from exc


@router.post(
    "/{group_jid}/members",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to group",
    description="Add a member to the WhatsApp group.",
)
async def add_member(
    group_jid: str,
    body: GroupMemberRequest,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    member_jid = _parse_jid(body.member_jid)
    try:
        await manage_group_uc.add_member(jid, member_jid)
        return SuccessResponse(message=f"Member {body.member_jid} added to group")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to add member", group_jid=group_jid, member=body.member_jid, error=str(exc), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add member") from exc


@router.delete(
    "/{group_jid}/members/{member_jid}",
    response_model=SuccessResponse,
    summary="Kick member from group",
    description="Remove (kick) a member from the WhatsApp group.",
)
async def kick_member(
    group_jid: str,
    member_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    m_jid = _parse_jid(member_jid)
    try:
        await manage_group_uc.kick_member(jid, m_jid)
        return SuccessResponse(message=f"Member {member_jid} removed from group")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to kick member", group_jid=group_jid, member=member_jid, error=str(exc), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to kick member") from exc


@router.post(
    "/{group_jid}/members/{member_jid}/promote",
    response_model=SuccessResponse,
    summary="Promote member to admin",
    description="Promote a group member to admin role.",
)
async def promote_member(
    group_jid: str,
    member_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    m_jid = _parse_jid(member_jid)
    try:
        await manage_group_uc.promote_member(jid, m_jid)
        return SuccessResponse(message=f"Member {member_jid} promoted to admin")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to promote member", group_jid=group_jid, member=member_jid, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to promote member"
        ) from exc


@router.post(
    "/{group_jid}/members/{member_jid}/demote",
    response_model=SuccessResponse,
    summary="Demote admin to member",
    description="Demote a group admin back to regular member.",
)
async def demote_member(
    group_jid: str,
    member_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    m_jid = _parse_jid(member_jid)
    try:
        await manage_group_uc.demote_member(jid, m_jid)
        return SuccessResponse(message=f"Member {member_jid} demoted to regular member")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to demote member", group_jid=group_jid, member=member_jid, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to demote member"
        ) from exc


@router.put(
    "/{group_jid}/name",
    response_model=SuccessResponse,
    summary="Rename group",
    description="Change the display name (subject) of a WhatsApp group.",
)
async def rename_group(
    group_jid: str,
    body: GroupRenameRequest,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    try:
        await manage_group_uc.change_group_name(jid, body.name)
        return SuccessResponse(message=f"Group renamed to '{body.name}'")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to rename group", group_jid=group_jid, name=body.name, error=str(exc), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rename group") from exc


@router.post(
    "/{group_jid}/leave",
    response_model=SuccessResponse,
    summary="Leave group",
    description="Make the bot leave the specified WhatsApp group.",
)
async def leave_group(
    group_jid: str,
    manage_group_uc: Annotated[GroupManagementUseCase, Depends(get_manage_group_uc)],
) -> SuccessResponse:
    jid = _parse_group_jid(group_jid)
    try:
        await manage_group_uc.leave_group(jid)
        return SuccessResponse(message="Left the group successfully")
    except GatewayException as exc:
        raise _map_gateway_exc(exc) from exc
    except Exception as exc:
        logger.error("Failed to leave group", group_jid=group_jid, error=str(exc), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to leave group") from exc
