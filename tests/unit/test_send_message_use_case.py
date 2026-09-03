"""Unit tests for SendMessageUseCase with mocked dependencies."""

from unittest.mock import AsyncMock

import pytest

from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase


@pytest.mark.asyncio
async def test_send_message_use_case_calls_gateway():
    mock_gateway = AsyncMock()
    mock_gateway.send_text = AsyncMock(return_value="msg-id-001")

    mock_message_repo = AsyncMock()
    mock_message_repo.save = AsyncMock()

    mock_event_bus = AsyncMock()
    mock_event_bus.publish = AsyncMock()

    use_case = SendMessageUseCase(mock_gateway, mock_message_repo, mock_event_bus)
    msg = await use_case.execute("628123456789@s.whatsapp.net", "Hello, World!")

    mock_gateway.send_text.assert_awaited_once()
    mock_message_repo.save.assert_awaited_once_with(msg)
    mock_event_bus.publish.assert_awaited_once()

    assert msg.id == "msg-id-001"
    assert msg.is_from_me is True
