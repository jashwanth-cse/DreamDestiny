"""
Abstract interface for the Transport provider.

Covers both bus and train search because they share the
same orchestration contract from the planner's perspective.
The concrete client decides which downstream service to call.
"""

from abc import ABC, abstractmethod

from app.schemas.context import BusContext, TrainContext


class BusProvider(ABC):
    """Fetches available buses for a route on a date."""

    @abstractmethod
    async def get_buses(
        self,
        source: str,
        destination: str,
        journey_date: str,         # DD-MM-YYYY
        limit: int = 10,
    ) -> list[BusContext]:
        """
        Return normalized buses.
        Returns [] on upstream failure — never raises.
        """
        ...


class TrainProvider(ABC):
    """Fetches available trains for a route on a date."""

    @abstractmethod
    async def get_trains(
        self,
        source: str,
        destination: str,
        journey_date: str,         # DD-MM-YYYY
    ) -> list[TrainContext]:
        """
        Return normalized trains.
        Returns [] on upstream failure — never raises.
        """
        ...
