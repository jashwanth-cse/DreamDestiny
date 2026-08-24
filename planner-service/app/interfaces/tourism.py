"""
Abstract interface for the Tourism provider.

The orchestrator depends on this interface, NOT on TourismClient directly.
Swap providers (or add mock/test doubles) by implementing this ABC.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.context import AttractionContext


class TourismProvider(ABC):
    """Fetches tourist attractions for a destination city."""

    @abstractmethod
    async def get_attractions(
        self,
        city: str,
        limit: int = 10,
    ) -> list[AttractionContext]:
        """
        Return normalized attractions for *city*.
        Returns [] on upstream failure — never raises.
        """
        ...
