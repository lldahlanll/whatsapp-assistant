"""CustomerLookupHandler — processes inbound WhatsApp messages for customer lookup queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.features.customer_lookup.formatter import format_reply, mask_phone
from whatsapp_platform.features.customer_lookup.phone_extractor import extract_phone_cores
from whatsapp_platform.infrastructure.customer_lookup.repository import (
    CustomerLookupRepository,
    CustomerLookupUnavailableError,
)

if TYPE_CHECKING:
    from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
    from whatsapp_platform.features.customer_lookup.rate_guard import PerSenderRateGuard
    from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class CustomerLookupHandler:
    """Listens for MessageReceived events in allowed WhatsApp groups and replies with customer info."""

    def __init__(
        self,
        repository: CustomerLookupRepository,
        send_msg_uc: SendMessageUseCase,
        rate_guard: PerSenderRateGuard,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.send_msg_uc = send_msg_uc
        self.rate_guard = rate_guard
        self.settings = settings

    async def on_message_received(self, event: MessageReceived) -> None:
        """Handle inbound WhatsApp message for Customer Lookup."""
        msg = event.message
        if not msg or msg.is_from_me:
            return

        chat_jid_str = str(msg.chat_jid)
        sender_jid_str = str(msg.sender_jid)

        # 1. Group whitelist guard: if customer_lookup_allowed_groups is specified, check whitelist
        if (
            self.settings.customer_lookup_allowed_groups
            and chat_jid_str not in self.settings.customer_lookup_allowed_groups
        ):
            return

        # 2. Content guard: text content only, skip bot commands
        if not isinstance(msg.content, TextContent):
            return

        text = msg.content.text.strip()
        if not text or text.startswith(self.settings.command_prefix):
            return

        # 3. Extract up to 5 normalized phone cores from text
        phone_cores = extract_phone_cores(text)
        if not phone_cores:
            return

        # 4. Per-sender rate guard to prevent customer data enumeration
        allowed = await self.rate_guard.check_and_record(sender_jid_str)
        if not allowed:
            logger.warning(
                "Customer lookup rate limit exceeded for sender",
                sender=sender_jid_str,
                group=chat_jid_str,
                message_id=msg.id,
            )
            return

        # 5. Process each extracted phone core (max 5)
        raw_msg = getattr(event, "raw_message", None) or getattr(msg, "raw_message", None)
        quoted_target = raw_msg or msg.id

        for phone_core in phone_cores:
            try:
                records = await self.repository.find_by_phone_suffix(phone_core)
            except CustomerLookupUnavailableError:
                logger.warning(
                    "Customer lookup database query unavailable",
                    phone_core_masked=mask_phone(phone_core),
                    sender_jid=sender_jid_str,
                    group_jid=chat_jid_str,
                )
                continue  # Do not crash loop if one query fails

            # Audit log (PII masked for phone number)
            logger.info(
                "Customer lookup performed",
                sender_jid=sender_jid_str,
                group_jid=chat_jid_str,
                phone_core_masked=mask_phone(phone_core),
                result_count=len(records),
            )

            reply = format_reply(records, query_phone_core=phone_core)
            await self.send_msg_uc.execute(chat_jid_str, reply, quoted=quoted_target)
