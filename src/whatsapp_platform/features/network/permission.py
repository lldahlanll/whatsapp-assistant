"""Permission and access control for Network AI."""

from __future__ import annotations

from typing import cast

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.infrastructure.config.settings import Settings


class NetworkPermissionChecker:
    """Checks whether a user or chat has permission to execute Network AI tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def has_network_read_permission(self, sender_jid: JID, chat_jid: JID | None = None) -> bool:
        """Verify network_read permission based on whitelist configuration.

        Either the sender JID/number or the chat JID (for group chats) must be in
        NETWORK_ALLOWED_JIDS. If that list is empty, AI_ADMIN_JIDS is used instead.
        If both are empty, nobody is allowed (router data is sensitive).
        """
        allowed_jids = cast(list[str], self._settings.network_allowed_jids) or cast(
            list[str], self._settings.ai_admin_jids
        )
        if not allowed_jids:
            return False

        sender_str = str(sender_jid)
        sender_phone = sender_jid.user

        if sender_str in allowed_jids or sender_phone in allowed_jids:
            return True

        if chat_jid:
            chat_str = str(chat_jid)
            if chat_str in allowed_jids:
                return True

        return False
