"""
Abstract interface for the Flight provider.
"""

from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.context import FlightContext


class FlightProvider(ABC):
    """Fetches available flights for a route on given dates."""

    @abstractmethod
    async def get_flights(
        self,
        origin: str,
        destination: str,
        outbound_date: str,
        return_date: Optional[str] = None,
        travelers: int = 1,
        travel_class: Optional[str] = "economy",
    ) -> list[FlightContext]:
        """
        Return normalized flights.
        Returns [] on upstream failure — never raises.
        """
        ...
