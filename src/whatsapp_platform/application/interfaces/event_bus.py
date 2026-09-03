"""IEventBus abstract interface."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from whatsapp_platform.domain.events.base import DomainEvent

E = TypeVar("E", bound=DomainEvent)
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class IEventBus(ABC):
    @abstractmethod
    def subscribe(self, event_class: type[E], handler: EventHandler) -> None:
        pass

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        pass
