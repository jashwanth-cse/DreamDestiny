"""
Abstract interface for the Hotel provider.
"""

from abc import ABC, abstractmethod

from app.schemas.context import HotelContext


class HotelProvider(ABC):
    """Fetches available hotels for a destination."""

    @abstractmethod
    async def get_hotels(
        self,
        city: str,
        check_in: str,
        check_out: str,
        adults: int,
        children: int = 0,
    ) -> list[HotelContext]:
        """
        Return normalized hotels.
        Returns [] on upstream failure — never raises.
        """
        ...
