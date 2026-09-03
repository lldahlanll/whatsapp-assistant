"""Unit tests for PerChatRateGuard."""

import asyncio

import pytest

from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard


@pytest.mark.asyncio
async def test_per_chat_rate_guard_blocks_burst():
    guard = PerChatRateGuard(max_requests=3, window_seconds=60.0)

    # 3 allowed
    assert await guard.check_and_record("chat1") is True
    assert await guard.check_and_record("chat1") is True
    assert await guard.check_and_record("chat1") is True

    # 4th blocked
    assert await guard.check_and_record("chat1") is False

    # Different chat still allowed
    assert await guard.check_and_record("chat2") is True


@pytest.mark.asyncio
async def test_per_chat_rate_guard_resets_after_window():
    guard = PerChatRateGuard(max_requests=1, window_seconds=0.05)

    assert await guard.check_and_record("chat1") is True
    assert await guard.check_and_record("chat1") is False

    await asyncio.sleep(0.08)

    # Allowed again after window!
    assert await guard.check_and_record("chat1") is True
