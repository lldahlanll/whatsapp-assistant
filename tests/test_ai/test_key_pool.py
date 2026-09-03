"""Unit tests for KeyPool key rotation and cooldown tracking."""

import time

import pytest

from whatsapp_platform.infrastructure.ai.key_pool import KeyPool


@pytest.mark.asyncio
async def test_key_pool_round_robin():
    pool = KeyPool(["key-1", "key-2", "key-3"], default_cooldown_seconds=60.0)
    assert pool.size() == 3

    k1 = await pool.next_available_key()
    assert k1 == (0, "key-1")

    k2 = await pool.next_available_key()
    assert k2 == (1, "key-2")

    k3 = await pool.next_available_key()
    assert k3 == (2, "key-3")

    # Wraps around to 0
    k4 = await pool.next_available_key()
    assert k4 == (0, "key-1")


@pytest.mark.asyncio
async def test_key_pool_cooldown_and_skip():
    pool = KeyPool(["key-1", "key-2"], default_cooldown_seconds=10.0)

    # Cool down key 0 for 10s
    await pool.mark_rate_limited(0, retry_after_seconds=10.0)

    # Next key should skip key 0 and return key 1
    k = await pool.next_available_key()
    assert k == (1, "key-2")

    # Next key should still skip key 0 and return key 1 again
    k_next = await pool.next_available_key()
    assert k_next == (1, "key-2")


@pytest.mark.asyncio
async def test_key_pool_respects_retry_after():
    pool = KeyPool(["key-1"], default_cooldown_seconds=60.0)

    await pool.mark_rate_limited(0, retry_after_seconds=120.0)
    cooldown_until = await pool.cooldown_until_for(0)

    # Should be approximately current monotonic time + 120s
    now = time.monotonic()
    assert cooldown_until > now + 100.0


@pytest.mark.asyncio
async def test_key_pool_all_cooling_detection():
    pool = KeyPool(["key-1", "key-2"], default_cooldown_seconds=60.0)

    assert not await pool.is_all_cooling()

    await pool.mark_rate_limited(0, 60.0)
    assert not await pool.is_all_cooling()

    await pool.mark_rate_limited(1, 60.0)
    assert await pool.is_all_cooling()

    assert await pool.next_available_key() is None


@pytest.mark.asyncio
async def test_key_pool_recovery_after_expiry():
    """C10 recovery test: confirms key is available again once cooldown expires."""
    pool = KeyPool(["key-1"], default_cooldown_seconds=0.1)

    # Cool down key 0 for 0.05 seconds
    await pool.mark_rate_limited(0, retry_after_seconds=0.05)
    assert await pool.next_available_key() is None

    # Wait for cooldown to expire
    import asyncio
    await asyncio.sleep(0.08)

    # Key 0 should be ready again!
    k = await pool.next_available_key()
    assert k == (0, "key-1")
