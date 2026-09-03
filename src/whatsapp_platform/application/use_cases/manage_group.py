"""GroupManagementUseCase for orchestrating group management operations."""

import structlog

from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.domain.exceptions.exceptions import GatewayException
from whatsapp_platform.domain.value_objects.jid import JID

logger = structlog.get_logger()


class GroupManagementUseCase:
    def __init__(self, gateway: IMessagingGateway) -> None:
        self.gateway = gateway

    async def get_group_info(self, group_jid: JID) -> dict:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        return await self.gateway.get_group_info(group_jid)

    async def get_invite_link(self, group_jid: JID, revoke: bool = False) -> str:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        return await self.gateway.get_group_invite_link(group_jid, revoke=revoke)

    async def add_member(self, group_jid: JID, member_jid: JID) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        await self.gateway.update_group_participants(
            group_jid, [member_jid], action="add"
        )

    async def kick_member(self, group_jid: JID, member_jid: JID) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        await self.gateway.update_group_participants(
            group_jid, [member_jid], action="remove"
        )

    async def promote_member(self, group_jid: JID, member_jid: JID) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        await self.gateway.update_group_participants(
            group_jid, [member_jid], action="promote"
        )

    async def demote_member(self, group_jid: JID, member_jid: JID) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        await self.gateway.update_group_participants(
            group_jid, [member_jid], action="demote"
        )

    async def change_group_name(self, group_jid: JID, name: str) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        if not name.strip():
            raise GatewayException("Group name cannot be empty")
        await self.gateway.set_group_name(group_jid, name.strip())

    async def leave_group(self, group_jid: JID) -> None:
        if not group_jid.is_group:
            raise GatewayException("Target JID is not a group")
        await self.gateway.leave_group(group_jid)
