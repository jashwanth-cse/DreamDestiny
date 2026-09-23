"""
Preference-derived parameters.

This module translates TripRequest preferences into the concrete
query parameters that each downstream service needs.

SOLID note: this is the ONLY place where preference-to-parameter
mapping lives. The orchestrator calls this; it does NOT compute
parameters itself. Adding a new preference type means changing
only this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas.request import TripRequest


@dataclass(frozen=True)
class TourismParams:
    city: str
    limit: int


@dataclass(frozen=True)
class HotelParams:
    city: str
    check_in: str    # YYYY-MM-DD (hotel-service format)
    check_out: str   # YYYY-MM-DD
    adults: int
    children: int


@dataclass(frozen=True)
class TransportParams:
    source: str
    destination: str
    outbound_date: str   # DD-MM-YYYY (bus/train service format)
    return_date: str     # DD-MM-YYYY


@dataclass(frozen=True)
class RouteParams:
    origin: str
    destination: str


@dataclass(frozen=True)
class FlightParams:
    origin: str
    destination: str
    outbound_date: str   # YYYY-MM-DD (Google Flights format)
    return_date: str     # YYYY-MM-DD
    travelers: int
    travel_class: str


def _to_service_date(d: date) -> str:
    """Convert Python date to DD-MM-YYYY (bus/train service format)."""
    return d.strftime("%d-%m-%Y")


def resolve_tourism_params(trip: TripRequest) -> TourismParams:
    pace = trip.preferences.activities.pace.value
    # More attractions for intensive pace, fewer for relaxed
    limit_map = {"relaxed": 8, "moderate": 12, "intensive": 20}
    return TourismParams(
        city=trip.destination,
        limit=limit_map.get(pace, 12),
    )


def resolve_hotel_params(trip: TripRequest) -> HotelParams:
    return HotelParams(
        city=trip.destination,
        check_in=trip.start_date.isoformat(),   # YYYY-MM-DD
        check_out=trip.end_date.isoformat(),     # YYYY-MM-DD
        adults=trip.travelers,
        children=0,
    )


def resolve_transport_params(trip: TripRequest) -> TransportParams:
    # Return trip departs on end_date
    return TransportParams(
        source=trip.origin,
        destination=trip.destination,
        outbound_date=_to_service_date(trip.start_date),
        return_date=_to_service_date(trip.end_date),
    )


def resolve_flight_params(trip: TripRequest) -> FlightParams:
    # Map berth preference / class to flight travel class if applicable
    berth_pref = trip.preferences.transport.berth_preference
    berth_val = berth_pref.value if berth_pref else "any"
    if berth_val in ("1A", "first"):
        travel_class = "first"
    elif berth_val in ("2A", "business"):
        travel_class = "business"
    elif berth_val in ("3A", "premium"):
        travel_class = "premium_economy"
    else:
        travel_class = "economy"

    return FlightParams(
        origin=trip.origin,
        destination=trip.destination,
        outbound_date=trip.start_date.isoformat(),
        return_date=trip.end_date.isoformat(),
        travelers=trip.travelers,
        travel_class=travel_class,
    )


def resolve_route_params(trip: TripRequest) -> RouteParams:
    return RouteParams(
        origin=trip.origin,
        destination=trip.destination,
    )
