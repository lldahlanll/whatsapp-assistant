"""Integration tests for CustomerLookupHandler."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.customer_lookup.handler import CustomerLookupHandler
from whatsapp_platform.features.customer_lookup.rate_guard import PerSenderRateGuard
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.customer_lookup.models import CustomerRecord
from whatsapp_platform.infrastructure.customer_lookup.repository import (
    CustomerLookupUnavailableError,
)


@pytest.fixture
def allowed_group_jid() -> str:
    return "12036301234567890@g.us"


@pytest.fixture
def settings(allowed_group_jid: str) -> Settings:
    return Settings(
        customer_lookup_allowed_groups=[allowed_group_jid],
        command_prefix="!",
    )


@pytest.fixture
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.find_by_phone_suffix = AsyncMock()
    return repo


@pytest.fixture
def mock_send_uc() -> MagicMock:
    uc = MagicMock()
    uc.execute = AsyncMock()
    return uc


@pytest.fixture
def rate_guard() -> PerSenderRateGuard:
    return PerSenderRateGuard(max_requests=5, window_seconds=60.0)


def create_message_received_event(
    text: str,
    chat_jid_str: str,
    sender_jid_str: str = "628111111111@s.whatsapp.net",
    is_from_me: bool = False,
) -> MessageReceived:
    msg = Message(
        id="MSG-100",
        chat_jid=JID.parse(chat_jid_str),
        sender_jid=JID.parse(sender_jid_str),
        content=TextContent(text=text),
        direction=MessageDirection.INBOUND if not is_from_me else MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        timestamp=datetime.now(),
        is_from_me=is_from_me,
    )
    return MessageReceived(message=msg)


@pytest.mark.asyncio
async def test_handler_allowed_group_valid_phone(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
    settings: Settings,
    allowed_group_jid: str,
) -> None:
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=settings,
    )

    rec = CustomerRecord(
        kode_kustomer="CUST-001",
        no_hp="08123456789",
        add_user="BUDI",
        add_date=datetime(2026, 5, 10),
    )
    mock_repo.find_by_phone_suffix.return_value = [rec]

    event = create_message_received_event(
        text="Cek nomor 08123456789 min",
        chat_jid_str=allowed_group_jid,
    )

    await handler.on_message_received(event)

    mock_repo.find_by_phone_suffix.assert_called_once_with("8123456789")
    reply_args = mock_send_uc.execute.call_args[0]
    assert reply_args[0] == allowed_group_jid
    assert reply_args[1] == "CUST-001"


@pytest.mark.asyncio
async def test_handler_disallowed_group_ignored(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
    settings: Settings,
) -> None:
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=settings,
    )

    event = create_message_received_event(
        text="Cek nomor 08123456789 min",
        chat_jid_str="unknown_group@g.us",
    )

    await handler.on_message_received(event)

    mock_repo.find_by_phone_suffix.assert_not_called()
    mock_send_uc.execute.assert_not_called()


@pytest.mark.asyncio
async def test_handler_empty_allowed_groups_allows_any_chat(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
) -> None:
    empty_settings = Settings(
        customer_lookup_allowed_groups=[],
        command_prefix="!",
    )
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=empty_settings,
    )

    rec = CustomerRecord(
        kode_kustomer="CUST-002",
        no_hp="08123456789",
        add_user="BAMBANG",
        add_date=datetime(2026, 5, 10),
    )
    mock_repo.find_by_phone_suffix.return_value = [rec]

    event = create_message_received_event(
        text="Cek nomor 08123456789 min",
        chat_jid_str="any_group_123@g.us",
    )

    await handler.on_message_received(event)

    mock_repo.find_by_phone_suffix.assert_called_once_with("8123456789")
    mock_send_uc.execute.assert_called_once()



@pytest.mark.asyncio
async def test_handler_command_prefix_ignored(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
    settings: Settings,
    allowed_group_jid: str,
) -> None:
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=settings,
    )

    event = create_message_received_event(
        text="!cek 08123456789",
        chat_jid_str=allowed_group_jid,
    )

    await handler.on_message_received(event)

    mock_repo.find_by_phone_suffix.assert_not_called()
    mock_send_uc.execute.assert_not_called()


@pytest.mark.asyncio
async def test_handler_max_5_phones_processed(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
    settings: Settings,
    allowed_group_jid: str,
) -> None:
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=settings,
    )
    mock_repo.find_by_phone_suffix.return_value = []

    text = (
        "08123456781 08123456782 08123456783 "
        "08123456784 08123456785 08123456786 08123456787"
    )
    event = create_message_received_event(
        text=text,
        chat_jid_str=allowed_group_jid,
    )

    await handler.on_message_received(event)

    assert mock_repo.find_by_phone_suffix.call_count == 5
    assert mock_send_uc.execute.call_count == 5


@pytest.mark.asyncio
async def test_handler_db_failure_gracefully_handled(
    mock_repo: MagicMock,
    mock_send_uc: MagicMock,
    rate_guard: PerSenderRateGuard,
    settings: Settings,
    allowed_group_jid: str,
) -> None:
    handler = CustomerLookupHandler(
        repository=mock_repo,
        send_msg_uc=mock_send_uc,
        rate_guard=rate_guard,
        settings=settings,
    )
    mock_repo.find_by_phone_suffix.side_effect = CustomerLookupUnavailableError("DB Error")

    event = create_message_received_event(
        text="Cek nomor 08123456789",
        chat_jid_str=allowed_group_jid,
    )

    # Should not raise exception
    await handler.on_message_received(event)

    mock_repo.find_by_phone_suffix.assert_called_once()
    mock_send_uc.execute.assert_not_called()
