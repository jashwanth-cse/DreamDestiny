"""
Pydantic Response Schemas for Flight Search.
Normalized, clean data models isolating upstream provider-specific structures.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class AirportInfo(BaseModel):
    """Airport information for departure or arrival."""
    id: str = Field(..., description="IATA airport code (e.g. 'MAA')")
    name: Optional[str] = Field(default=None, description="Airport name (e.g. 'Chennai International Airport')")
    time: Optional[str] = Field(default=None, description="Local departure/arrival datetime (e.g. '2026-10-15 09:55')")


class FlightSegment(BaseModel):
    """Detailed information for an individual flight leg/segment."""
    airline: Optional[str] = None
    airline_logo: Optional[str] = None
    flight_number: Optional[str] = None
    airplane: Optional[str] = None
    travel_class: Optional[str] = None
    legroom: Optional[str] = None
    departure_airport: AirportInfo
    arrival_airport: AirportInfo
    duration_minutes: Optional[int] = None
    extensions: List[str] = Field(default_factory=list)


class LayoverInfo(BaseModel):
    """Information about a layover between connecting flights."""
    name: Optional[str] = None
    id: Optional[str] = None
    duration_minutes: Optional[int] = None


class CarbonEmissions(BaseModel):
    """Carbon emissions metrics if provided by Google Flights."""
    this_flight_grams: Optional[int] = None
    typical_for_route_grams: Optional[int] = None
    difference_percent: Optional[int] = None


class Flight(BaseModel):
    """
    A single normalized flight option (direct or multi-segment).
    Combines best_flights and other_flights from SerpApi.
    """
    flight_id: str = Field(..., description="Unique stable flight identifier")
    airline: Optional[str] = Field(default=None, description="Primary airline name")
    airline_logo: Optional[str] = Field(default=None, description="URL of airline logo")
    flight_number: Optional[str] = Field(default=None, description="Flight number(s), e.g. '6E 479'")
    
    departure_airport: AirportInfo = Field(..., description="Origin airport details")
    arrival_airport: AirportInfo = Field(..., description="Destination airport details")
    
    departure_time: Optional[str] = Field(default=None, description="Departure time string")
    arrival_time: Optional[str] = Field(default=None, description="Arrival time string")
    
    duration_minutes: Optional[int] = Field(default=None, description="Total journey duration in minutes")
    duration: Optional[str] = Field(default=None, description="Human readable duration (e.g. '1h 5m')")
    
    stops: int = Field(default=0, description="Number of stops (0 = nonstop/direct)")
    
    price: Optional[float] = Field(default=None, description="Total ticket price")
    currency: str = Field(default="INR", description="Currency code")
    
    travel_class: Optional[str] = Field(default=None, description="Travel class (e.g. 'Economy')")
    
    booking_token: Optional[str] = Field(default=None, description="SerpApi booking token when available")
    departure_token: Optional[str] = Field(default=None, description="SerpApi departure token when available")
    
    is_best_flight: bool = Field(default=False, description="True if ranked as Best Flight by Google Flights")
    
    segments: List[FlightSegment] = Field(default_factory=list, description="Subsegments for connecting flights")
    layovers: List[LayoverInfo] = Field(default_factory=list, description="Layover details for multi-leg journeys")
    carbon_emissions: Optional[CarbonEmissions] = Field(default=None, description="Estimated emissions data")


class FlightSearchData(BaseModel):
    """Payload data returned in FlightSearchResponse."""
    origin: str = Field(..., description="Resolved origin IATA code")
    origin_name: Optional[str] = Field(default=None, description="Resolved origin airport name")
    origin_city: Optional[str] = Field(default=None, description="Original city name as queried")
    origin_airport_distance_km: Optional[float] = Field(
        default=None,
        description=(
            "Distance (km) from the queried origin city to the resolved airport. "
            "null when the city has its own airport or the query was a direct IATA code."
        ),
    )
    destination: str = Field(..., description="Resolved destination IATA code")
    destination_name: Optional[str] = Field(default=None, description="Resolved destination airport name")
    destination_city: Optional[str] = Field(default=None, description="Original city name as queried")
    destination_airport_distance_km: Optional[float] = Field(
        default=None,
        description=(
            "Distance (km) from the queried destination city to the resolved airport. "
            "null when the city has its own airport or the query was a direct IATA code."
        ),
    )
    outbound_date: str = Field(..., description="Outbound date (YYYY-MM-DD)")
    return_date: Optional[str] = Field(default=None, description="Return date if round-trip")
    trip_type: str = Field(default="one_way", description="'one_way' or 'round_trip'")
    total_flights: int = Field(default=0, description="Total number of combined flight options")
    best_flights_count: int = Field(default=0, description="Number of best flights")
    other_flights_count: int = Field(default=0, description="Number of other flights")
    flights: List[Flight] = Field(default_factory=list, description="Normalized flight options")


class FlightSearchResponse(BaseModel):
    """Standard microservice response envelope."""
    success: bool = True
    message: str = "Flight search successful"
    data: Optional[FlightSearchData] = None


class ErrorResponse(BaseModel):
    """Standard error response envelope."""
    success: bool = False
    message: str
    error_code: Optional[str] = None
