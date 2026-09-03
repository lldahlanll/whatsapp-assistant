"""IContainer abstract interface for DI container."""

from abc import ABC, abstractmethod
from typing import TypeVar

T = TypeVar("T")


class IContainer(ABC):
    @abstractmethod
    def resolve(self, interface: type[T]) -> T:
        pass
