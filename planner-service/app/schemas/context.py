"""
TripContext schema — the aggregated output of the orchestrator.

Design principles:
  - Every domain section is Optional[...] = None.
  - Adding a new service domain (restaurants, flights, weather, etc.)
    is always non-breaking: just add a new Optional field with a default.
  - The orchestrator always returns a valid TripContext even if some
    services are unavailable — missing sections are simply None / [].
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.request import TripRequest


# ── Normalized domain models ──────────────────────────────────────────────────
# These mirror the exact response shapes of each downstream service.
# They live here so the planner owns the contract; services are providers.


class AttractionContext(BaseModel):
    """Mirrors tourism-service Attraction model."""
    name: str
    address: str
    rating: Optional[float] = None
    review_count: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    types: list[str] = Field(default_factory=list)


class HotelPriceContext(BaseModel):
    """Mirrors hotel-service PriceModel."""
    per_night: Optional[float] = None
    total: Optional[float] = None
    currency: str = "INR"


class HotelContext(BaseModel):
    """Mirrors hotel-service HotelModel."""
    id: str
    name: str
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    hotel_class: Optional[int] = None
    price: HotelPriceContext = Field(default_factory=HotelPriceContext)
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    amenities: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    website_url: Optional[str] = None
    nearby_places: list[str] = Field(default_factory=list)


class BusContext(BaseModel):
    """Key fields from transport-service Bus model, normalized for planning."""
    operator_name: Optional[str] = None
    bus_type: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    duration: Optional[str] = None
    minimum_fare: Optional[float] = None
    maximum_fare: Optional[float] = None
    available_seats: Optional[int] = None
    amenities: list[str] = Field(default_factory=list)
    rating: Optional[float] = None
    boarding_point: Optional[str] = None
    dropping_point: Optional[str] = None


class TravelClassContext(BaseModel):
    """Mirrors train-service TravelClass."""
    travel_class: str
    fare: int
    availability: str
    bookable: bool


class TrainContext(BaseModel):
    """Key fields from transport-service Train model, normalized for planning."""
    train_number: str
    train_name: str
    train_type: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    duration: str
    distance_km: int
    lowest_fare: int
    rating: float
    has_pantry: bool
    running_days: list[str] = Field(default_factory=list)
    recommended_class: Optional[TravelClassContext] = None
    classes: list[TravelClassContext] = Field(default_factory=list)


class RouteModeContext(BaseModel):
    """Mirrors route-service RouteMode."""
    mode: str
    duration_minutes: Optional[int] = None


class RouteContext(BaseModel):
    """Mirrors route-service RouteResponse."""
    origin: str
    destination: str
    distance_km: Optional[float] = None
    routes: list[RouteModeContext] = Field(default_factory=list)


# ── Service availability metadata ─────────────────────────────────────────────

class ServiceStatus(BaseModel):
    """
    Records which services responded successfully.
    Allows consumers to understand partial results.
    """
    tourism:  bool = False
    hotels:   bool = False
    buses:    bool = False
    trains:   bool = False
    route:    bool = False
    # New services added here with False default — never breaks callers


# ── TripContext ───────────────────────────────────────────────────────────────

class TripContext(BaseModel):
    """
    The complete aggregated context for a planned trip.

    EXTENSIBILITY CONTRACT:
    - Every domain section is Optional with a default.
    - To add a new domain (flights, restaurants, weather, activities):
        1. Add a normalized model above.
        2. Add an Optional field here with a default.
        3. Add the client + interface.
        4. Gather concurrently in the orchestrator.
      → Existing API consumers see no breaking change.
    """

    # ── Core trip metadata ────────────────────────────────────────────────
    trip: TripRequest

    # ── Tourism ───────────────────────────────────────────────────────────
    attractions: list[AttractionContext] = Field(default_factory=list)

    # ── Hotels ────────────────────────────────────────────────────────────
    hotels: list[HotelContext] = Field(default_factory=list)

    # ── Transport — Bus ───────────────────────────────────────────────────
    outbound_buses: list[BusContext] = Field(default_factory=list)
    return_buses:   list[BusContext] = Field(default_factory=list)

    # ── Transport — Train ─────────────────────────────────────────────────
    outbound_trains: list[TrainContext] = Field(default_factory=list)
    return_trains:   list[TrainContext] = Field(default_factory=list)

    # ── Route / Distance ──────────────────────────────────────────────────
    route: Optional[RouteContext] = None

    # ── Future domains — add here without breaking contract ───────────────
    # restaurants:  Optional[list[RestaurantContext]] = None
    # flights:      Optional[list[FlightContext]]     = None
    # weather:      Optional[WeatherContext]          = None
    # activities:   Optional[list[ActivityContext]]   = None

    # ── Service availability metadata ─────────────────────────────────────
    service_status: ServiceStatus = Field(default_factory=ServiceStatus)
