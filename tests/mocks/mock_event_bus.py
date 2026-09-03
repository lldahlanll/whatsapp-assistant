"""MockEventBus for testing."""

from typing import TypeVar

from whatsapp_platform.application.interfaces.event_bus import EventHandler, IEventBus
from whatsapp_platform.domain.events.base import DomainEvent

E = TypeVar("E", bound=DomainEvent)


class MockEventBus(IEventBus):
    def __init__(self) -> None:
        self._subscriptions: dict[type[DomainEvent], list[EventHandler]] = {}
        self.published_events: list[DomainEvent] = []

    def subscribe(self, event_class: type[E], handler: EventHandler) -> None:
        if event_class not in self._subscriptions:
            self._subscriptions[event_class] = []
        self._subscriptions[event_class].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        self.published_events.append(event)
        handlers = self._subscriptions.get(type(event), [])
        for handler in handlers:
            await handler(event)
