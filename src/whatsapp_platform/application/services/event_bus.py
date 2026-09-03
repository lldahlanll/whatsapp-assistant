"""InMemoryEventBus implementation."""

import inspect
from collections import defaultdict
from typing import TypeVar

import structlog

from whatsapp_platform.application.interfaces.event_bus import EventHandler, IEventBus
from whatsapp_platform.domain.events.base import DomainEvent

E = TypeVar("E", bound=DomainEvent)
logger = structlog.get_logger()


class InMemoryEventBus(IEventBus):
    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(
            list
        )

    def subscribe(self, event_class: type[E], handler: EventHandler) -> None:
        self._subscribers[event_class].append(handler)
        logger.debug(
            "Subscribed to event",
            event_type=event_class.__name__,
            handler=handler.__name__,
        )

    async def publish(self, event: DomainEvent) -> None:
        event_class = type(event)
        handlers = self._subscribers.get(event_class, [])
        logger.info(
            "Publishing event",
            event_name=event.event_name,
            subscribers_count=len(handlers),
        )

        for handler in handlers:
            try:
                res = handler(event)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                logger.error(
                    "Error executing event handler",
                    event=event.event_name,
                    handler=handler.__name__,
                    error=str(exc),
                    exc_info=True,
                )
