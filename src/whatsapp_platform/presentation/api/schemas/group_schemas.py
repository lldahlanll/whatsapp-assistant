"""Pydantic schemas for group management API endpoints."""

from pydantic import BaseModel, Field


class GroupMemberRequest(BaseModel):
    """Request body for add/kick/promote/demote group member operations."""

    member_jid: str = Field(
        description="Member's JID (e.g. '628123456789@s.whatsapp.net')",
        examples=["628123456789@s.whatsapp.net"],
    )


class GroupRenameRequest(BaseModel):
    """Request body for renaming a group."""

    name: str = Field(
        description="New group name",
        min_length=1,
        max_length=25,
        examples=["My Awesome Group"],
    )


class GroupParticipantInfo(BaseModel):
    """Info about a single group participant."""

    jid: str = Field(description="Participant JID")
    is_admin: bool = Field(default=False, description="True if participant is group admin")
    is_super_admin: bool = Field(default=False, description="True if participant is super admin")


class GroupInfoResponse(BaseModel):
    """Response schema for group info."""

    jid: str = Field(description="Group JID")
    name: str = Field(default="", description="Group name/subject")
    description: str = Field(default="", description="Group description")
    participant_count: int = Field(default=0, description="Number of participants")
    participants: list[GroupParticipantInfo] = Field(
        default_factory=list, description="List of participants"
    )
    is_announce: bool = Field(default=False, description="True if only admins can send")
    is_locked: bool = Field(default=False, description="True if group settings are locked to admins")


class GroupInviteResponse(BaseModel):
    """Response schema for group invite link."""

    jid: str = Field(description="Group JID")
    invite_link: str = Field(description="WhatsApp group invite link")
