"""Provider selection strategy interface and default fixed-priority implementation.

Design:
- IProviderStrategy is injected into AIService so it can be swapped later for
  cost-based or latency-based routing without touching the orchestrator.
- FixedPriorityStrategy is the default: Gemini → Groq → OpenRouter.
  It skips providers marked unavailable (all keys cooling or no keys configured).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IProviderStrategy(ABC):
    """Interface for provider ordering strategies.

    AIService calls ordered_providers() on every generate_reply() invocation,
    passing in a dict of {provider_name: is_available} so the strategy can
    filter or reorder based on current state.
    """

    @abstractmethod
    def ordered_providers(self, available: dict[str, bool]) -> list[str]:
        """Return an ordered list of provider names to attempt.

        Args:
            available: Mapping of provider_name → True if it should be tried.
                       Providers with False should be skipped or deprioritized.

        Returns:
            Ordered list of provider names to attempt (filtered to available only).
        """


class FixedPriorityStrategy(IProviderStrategy):
    """Default strategy: attempt providers in a fixed priority order.

    Order: Gemini → Groq → OpenRouter (as specified in DEFAULT_PROVIDER_ORDER).
    Providers absent from the available dict (e.g. not configured) are skipped.

    Future: swap this for a LatencyBasedStrategy or CostBasedStrategy by
    implementing IProviderStrategy and injecting via container.py.
    """

    def __init__(self, priority_order: list[str]) -> None:
        self._order = priority_order

    def ordered_providers(self, available: dict[str, bool]) -> list[str]:
        """Return available providers in fixed priority order."""
        return [p for p in self._order if available.get(p, False)]
