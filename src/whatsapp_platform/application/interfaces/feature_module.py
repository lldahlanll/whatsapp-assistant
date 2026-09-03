"""IFeatureModule abstract interface for pluggable feature modules."""

from abc import ABC, abstractmethod
from typing import Any


class IFeatureModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the feature module."""

    @abstractmethod
    async def initialize(self, container: Any) -> None:
        """Initialize and register handlers using DI Container."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup module resources."""
