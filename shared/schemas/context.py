"""
TripContext — aggregated data assembled by the Trip Planner.

This is the shared envelope passed between planner components.
All list fields default to empty so partially-assembled contexts are valid
at any stage of planning.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.schemas.trip import TripRequest
from shared.schemas.attraction import Attraction
from shared.schemas.hotel import Hotel
from shared.schemas.transport import Bus, Train, RouteOption, FlightOption


class TripContext(BaseModel):
    """
    The full data context for a planned trip.

    Assembled by the Trip Planner by calling:
      - Tourism Service  → attractions
      - Hotel Service    → hotels
      - Transport Service (Bus)    → outbound_buses, return_buses
      - Transport Service (Train)  → outbound_trains, return_trains
      - Transport Service (Flight) → outbound_flights, return_flights, flights
    """

    # The original request that triggered planning
    trip: TripRequest = Field(..., description="The traveler's original trip request.")

    # Tourism Service output
    attractions: list[Attraction] = Field(
        default_factory=list,
        description="Tourist attractions at the destination."
    )

    # Hotel Service output
    hotels: list[Hotel] = Field(
        default_factory=list,
        description="Available hotels at the destination."
    )

    # Transport Service — Bus
    outbound_buses: list[Bus] = Field(
        default_factory=list,
        description="Bus options from origin to destination."
    )
    return_buses: list[Bus] = Field(
        default_factory=list,
        description="Bus options from destination back to origin."
    )

    # Transport Service — Train
    outbound_trains: list[Train] = Field(
        default_factory=list,
        description="Train options from origin to destination."
    )
    return_trains: list[Train] = Field(
        default_factory=list,
        description="Train options from destination back to origin."
    )

    # Transport Service — Flight
    outbound_flights: list[FlightOption] = Field(
        default_factory=list,
        description="Flight options from origin to destination."
    )
    return_flights: list[FlightOption] = Field(
        default_factory=list,
        description="Flight options from destination back to origin."
    )
    flights: list[FlightOption] = Field(
        default_factory=list,
        description="All aggregated flight options for the trip."
    )

    # Generic route / distance summaries
    routes: list[RouteOption] = Field(
        default_factory=list,
        description="Route distance/cost summaries between key points of the trip."
    )
