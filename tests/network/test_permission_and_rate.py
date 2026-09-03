"""Unit tests for Network AI permission checker and rate guard."""

import pytest

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.network.permission import NetworkPermissionChecker
from whatsapp_platform.features.network.rate_guard import NetworkRateGuard
from whatsapp_platform.infrastructure.config.settings import Settings


def test_permission_checker_empty_whitelist_allows_all() -> None:
    settings = Settings(network_allowed_jids=[])
    checker = NetworkPermissionChecker(settings)
    assert checker.has_network_read_permission(JID.parse("628123456789@s.whatsapp.net")) is True


def test_permission_checker_with_whitelist() -> None:
    settings = Settings(network_allowed_jids=["628123456789@s.whatsapp.net", "12036301234567890@g.us"])
    checker = NetworkPermissionChecker(settings)

    allowed_user = JID.parse("628123456789@s.whatsapp.net")
    denied_user = JID.parse("628999999999@s.whatsapp.net")
    allowed_group = JID.parse("12036301234567890@g.us")
    denied_group = JID.parse("12036309999999999@g.us")

    assert checker.has_network_read_permission(allowed_user) is True
    assert checker.has_network_read_permission(denied_user) is False
    # Allowed in allowed group even if user is not specifically whitelisted
    assert checker.has_network_read_permission(denied_user, chat_jid=allowed_group) is True
    assert checker.has_network_read_permission(denied_user, chat_jid=denied_group) is False



@pytest.mark.asyncio
async def test_rate_guard_sliding_window() -> None:
    guard = NetworkRateGuard(window_seconds=10.0)
    user = "628123456789@s.whatsapp.net"

    # Limit for SECURITY is 5
    for _ in range(5):
        assert await guard.check_and_record(user, "NETWORK_SECURITY") is True

    # 6th request within window should be rejected
    assert await guard.check_and_record(user, "NETWORK_SECURITY") is False
