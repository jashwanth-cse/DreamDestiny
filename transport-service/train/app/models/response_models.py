from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict


# ---------------------------------------------------------
# Station Models
# ---------------------------------------------------------

class Station(BaseModel):
    station_name: str
    station_code: str
    latitude: float
    longitude: float

class StationSearchResponse(BaseModel):
    success: bool
    message: str
    data: List[Station]

# ---------------------------------------------------------
# Train Models
# ---------------------------------------------------------

class StationSimple(BaseModel):
    code: str
    name: str

class TravelClass(BaseModel):
    travel_class: str
    fare: int
    availability: str
    prediction: int
    bookable: bool
    availability_source: str = "cached"  # "cached" | "live" | "unavailable"

class Train(BaseModel):
    train_number: str
    train_name: str
    train_type: str
    from_: StationSimple = Field(alias="from")
    to: StationSimple
    departure_time: str
    arrival_time: str
    duration_minutes: int
    duration: str
    distance: int
    running_days: List[str]
    rating: float
    has_pantry: bool
    lowest_fare: int
    recommended_class: Optional[TravelClass] = None
    classes: List[TravelClass]

class RouteStationInfo(BaseModel):
    station_name: str
    station_code: str
    division: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None

class TrainSearchData(BaseModel):
    result_type: str
    source: str
    destination: str
    total_trains: int
    trains: List[Train]
    route_type: str = "direct"  # "direct" | "division_fallback" | "state_capital_fallback" | "no_route_found"
    original_source: Optional[Dict[str, Any]] = None
    original_destination: Optional[Dict[str, Any]] = None
    actual_source: Optional[Dict[str, Any]] = None
    actual_destination: Optional[Dict[str, Any]] = None
    fallback_reason: Optional[str] = None
    fallback_searches_count: int = 1
    latency_ms: Optional[float] = None

class TrainSearchResponse(BaseModel):
    success: bool
    message: str
    data: TrainSearchData

# ---------------------------------------------------------
# Generic Models
# ---------------------------------------------------------

class ErrorResponse(BaseModel):
    success: bool
    message: str
