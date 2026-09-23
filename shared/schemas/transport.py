"""
Transport schemas — cover both Bus and Train services.

Source services : transport-service/bus   (RedBus provider)
                  transport-service/train  (IRCTC provider)

These schemas are intentionally kept close to the provider models so the
Trip Planner can consume either without additional mapping.

─────────────────────────────────────────────────────────────
BUS  →  transport-service/bus/app/models/response_models.py
─────────────────────────────────────────────────────────────
Key field mapping:
    operator_name     → operator_name
    operator_logo     → operator_logo
    service_id        → service_id
    service_name      → service_name
    bus_type          → bus_type
    departure_time    → departure_time   (YYYY-MM-DD HH:MM:SS)
    arrival_time      → arrival_time     (YYYY-MM-DD HH:MM:SS)
    duration_minutes  → duration_minutes
    duration          → duration         (human-readable, e.g. "6h 20m")
    minimum_fare      → minimum_fare
    maximum_fare      → maximum_fare
    fare_list         → fare_list
    available_seats   → available_seats
    boarding_point    → boarding_point
    dropping_point    → dropping_point
    amenities         → amenities
    rating            → rating
    review_count      → review_count
    live_tracking     → live_tracking
    metadata.doj      → journey_date (via BusMetadata)

─────────────────────────────────────────────────────────────
TRAIN  →  transport-service/train/app/models/response_models.py
─────────────────────────────────────────────────────────────
Key field mapping:
    train_number      → train_number
    train_name        → train_name
    train_type        → train_type
    from_.code/name   → source_code / source_name
    to.code/name      → destination_code / destination_name
    departure_time    → departure_time
    arrival_time      → arrival_time
    duration_minutes  → duration_minutes
    duration          → duration
    distance          → distance_km
    running_days      → running_days
    rating            → rating
    lowest_fare       → lowest_fare
    recommended_class → recommended_class (TravelClass)
    classes           → classes (list[TravelClass])
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ===========================================================================
# Shared sub-models
# ===========================================================================

class TravelClass(BaseModel):
    """
    A bookable class on a train.
    Mirrors transport-service/train/app/models/response_models.py → TravelClass.
    """
    travel_class: str = Field(..., description="Class code, e.g. SL, 3A, 2A, 1A.")
    fare: int = Field(..., description="Fare in INR.")
    availability: str = Field(..., description="Availability status string.")
    prediction: int = Field(
        ...,
        description="Predicted availability score (provider-specific integer)."
    )
    bookable: bool
    availability_source: str = Field(
        default="cached",
        description="Data freshness: cached | live | unavailable."
    )


class BusOffer(BaseModel):
    """
    An operator-level promotional offer on a bus.
    Mirrors transport-service/bus/app/models/response_models.py → BusOffer.
    """
    discount_value: Optional[str] = None
    discount_type: Optional[int] = None
    offer_type: Optional[int] = None
    validity_days: Optional[int] = None


# ===========================================================================
# Bus
# ===========================================================================

class Bus(BaseModel):
    """
    A single bus result.
    Mirrors transport-service/bus/app/models/response_models.py → Bus.
    """

    # Operator
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    operator_logo: Optional[str] = None

    # Service / route
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    route_id: Optional[int] = None

    # Bus type
    bus_type: Optional[str] = None
    bus_type_id: Optional[int] = None

    # Schedule
    departure_time: Optional[str] = Field(
        default=None,
        description="Departure datetime string (YYYY-MM-DD HH:MM:SS)."
    )
    arrival_time: Optional[str] = Field(
        default=None,
        description="Arrival datetime string (YYYY-MM-DD HH:MM:SS)."
    )
    duration_minutes: Optional[int] = None
    duration: Optional[str] = Field(
        default=None,
        description="Human-readable duration, e.g. '6h 20m'."
    )

    # Fares
    fare_list: list[float] = Field(default_factory=list)
    minimum_fare: Optional[float] = None
    maximum_fare: Optional[float] = None

    # Seats
    available_seats: Optional[int] = None
    window_seats: Optional[int] = None
    single_seats: Optional[int] = None
    upper_seats: Optional[int] = None
    lower_seats: Optional[int] = None

    # Boarding / Dropping
    boarding_point: Optional[str] = None
    boarding_count: Optional[int] = None
    dropping_point: Optional[str] = None
    dropping_count: Optional[int] = None

    # Amenities & offers
    amenities: list[str] = Field(default_factory=list)
    offers: list[BusOffer] = Field(default_factory=list)

    # Rating
    rating: Optional[float] = None
    review_count: Optional[int] = None

    # Features
    live_tracking: bool = False
    seat_layout_available: bool = False
    partial_cancellation: bool = False


# ===========================================================================
# Train
# ===========================================================================

class StationSimple(BaseModel):
    """
    Minimal station reference used inside a Train result.
    Mirrors transport-service/train/app/models/response_models.py → StationSimple.
    """
    code: str
    name: str


class Train(BaseModel):
    """
    A single train result.
    Mirrors transport-service/train/app/models/response_models.py → Train.
    """

    train_number: str
    train_name: str
    train_type: str

    # Source / destination (from Train model's from_ / to fields)
    source: StationSimple = Field(
        ...,
        description="Origin station (maps to Train.from_ / alias 'from')."
    )
    destination: StationSimple = Field(
        ...,
        description="Destination station (maps to Train.to)."
    )

    # Schedule
    departure_time: str
    arrival_time: str
    duration_minutes: int
    duration: str = Field(..., description="Human-readable duration, e.g. '7h 30m'.")

    # Route info
    distance_km: int = Field(
        ...,
        description="Route distance in km (maps to Train.distance)."
    )
    running_days: list[str] = Field(default_factory=list)

    # Pricing & availability
    rating: float
    has_pantry: bool
    lowest_fare: int
    recommended_class: Optional[TravelClass] = None
    classes: list[TravelClass] = Field(default_factory=list)


# ===========================================================================
# Route option (generic point-to-point distance/cost summary)
# ===========================================================================

class TransportMode(str):
    """Allowed transport mode strings."""
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    CAR = "car"
    FERRY = "ferry"
    OTHER = "other"


class RouteOption(BaseModel):
    """
    A generic route summary between two points.
    Used by the Trip Planner for distance/duration data,
    not tied to a specific provider.
    """

    source: str = Field(..., description="Origin place name or coordinates.")
    destination: str = Field(..., description="Destination place name or coordinates.")
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    mode: str = Field(
        default="car",
        description="Transport mode used for this route estimate."
    )


# ===========================================================================
# Flight
# ===========================================================================

class FlightOption(BaseModel):
    """
    A normalized flight option.
    Mirrors transport-service/flight/app/models/response_models.py -> Flight.
    """
    flight_id: str = Field(..., description="Unique stable flight identifier")
    airline: Optional[str] = Field(default=None, description="Primary airline name")
    airline_logo: Optional[str] = Field(default=None, description="URL of airline logo")
    flight_number: Optional[str] = Field(default=None, description="Flight number(s)")
    departure_airport_code: str = Field(..., description="Origin IATA code")
    departure_airport_name: Optional[str] = Field(default=None, description="Origin airport name")
    arrival_airport_code: str = Field(..., description="Destination IATA code")
    arrival_airport_name: Optional[str] = Field(default=None, description="Destination airport name")
    departure_time: Optional[str] = Field(default=None, description="Departure datetime string")
    arrival_time: Optional[str] = Field(default=None, description="Arrival datetime string")
    duration_minutes: Optional[int] = Field(default=None, description="Total journey duration in minutes")
    duration: Optional[str] = Field(default=None, description="Human readable duration, e.g. '1h 5m'")
    stops: int = Field(default=0, description="Number of stops (0 = nonstop/direct)")
    price: Optional[float] = Field(default=None, description="Ticket price")
    currency: str = Field(default="INR", description="Currency code")
    travel_class: Optional[str] = Field(default=None, description="Travel class (e.g. 'Economy')")
    booking_token: Optional[str] = Field(default=None, description="Provider booking token")
    departure_token: Optional[str] = Field(default=None, description="Provider departure token")
    is_best_flight: bool = Field(default=False, description="True if marked as Best Flight")

