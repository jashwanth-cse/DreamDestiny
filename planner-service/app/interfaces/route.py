"""
Abstract interface for the Route provider.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.context import RouteContext


class RouteProvider(ABC):
    """Fetches route distance and mode options between two locations."""

    @abstractmethod
    async def get_route(
        self,
        origin: str,
        destination: str,
    ) -> Optional[RouteContext]:
        """
        Return normalized route context.
        Returns None on upstream failure — never raises.
        """
        ...
