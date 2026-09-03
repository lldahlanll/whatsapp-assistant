"""Unit tests for InMemoryEventBus."""

import pytest

from whatsapp_platform.application.services.event_bus import InMemoryEventBus
from whatsapp_platform.domain.events.session_events import SessionConnected


@pytest.mark.asyncio
async def test_event_bus_publishes_to_subscriber():
    bus = InMemoryEventBus()
    received_events = []

    async def handler(event: SessionConnected):
        received_events.append(event)

    bus.subscribe(SessionConnected, handler)

    event = SessionConnected(session_id="sess-001", phone_number="628111")
    await bus.publish(event)

    assert len(received_events) == 1
    assert received_events[0].session_id == "sess-001"


@pytest.mark.asyncio
async def test_event_bus_no_subscribers_no_error():
    bus = InMemoryEventBus()
    event = SessionConnected(session_id="sess-001")
    # Should not raise
    await bus.publish(event)


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    bus = InMemoryEventBus()
    results = []

    async def handler_a(event):
        results.append("A")

    async def handler_b(event):
        results.append("B")

    bus.subscribe(SessionConnected, handler_a)
    bus.subscribe(SessionConnected, handler_b)

    await bus.publish(SessionConnected(session_id="sess-001"))
    assert "A" in results
    assert "B" in results
