"""
Abstract Base Provider for Flight Searches.
Defines the protocol/interface that any flight search provider (SerpApi, Amadeus, Duffel, etc.)
must implement, keeping the microservice loosely coupled.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple
from app.models.request_models import FlightSearchRequest
from app.models.response_models import Flight


class FlightProvider(ABC):
    """
    Abstract interface for flight search providers.
    """

    @abstractmethod
    async def search_flights(
        self,
        origin_code: str,
        destination_code: str,
        request: FlightSearchRequest
    ) -> Tuple[List[Flight], int, int, str]:
        """
        Executes search against the provider API.

        Returns:
            Tuple of:
            - combined_flights: List[Flight]
            - best_flights_count: int
            - other_flights_count: int
            - trip_type: str ('one_way' or 'round_trip')
        """
        pass
