"""
Pydantic Request Schemas for Flight Search.
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


class FlightSearchRequest(BaseModel):
    """
    Request payload for flight search.
    Supports both IATA airport codes (e.g. 'MAA', 'CJB')
    and city names (e.g. 'Chennai', 'Coimbatore').
    """
    origin: str = Field(
        ...,
        description="Origin airport IATA code (e.g. 'MAA') or city name (e.g. 'Chennai')"
    )
    destination: str = Field(
        ...,
        description="Destination airport IATA code (e.g. 'CJB') or city name (e.g. 'Coimbatore')"
    )
    outbound_date: str = Field(
        ...,
        description="Outbound journey date (YYYY-MM-DD or DD-MM-YYYY)"
    )
    return_date: Optional[str] = Field(
        default=None,
        description="Optional return journey date for round-trip search (YYYY-MM-DD or DD-MM-YYYY)"
    )
    travelers: int = Field(
        default=1,
        ge=1,
        le=9,
        description="Total number of travelers (maps to adults if not split)"
    )
    adults: Optional[int] = Field(
        default=None,
        ge=1,
        le=9,
        description="Number of adult passengers"
    )
    children: Optional[int] = Field(
        default=None,
        ge=0,
        le=8,
        description="Number of child passengers"
    )
    travel_class: Optional[Union[str, int]] = Field(
        default="economy",
        description="Travel class: 'economy', 'premium_economy', 'business', 'first' or 1-4"
    )
    stops: Optional[int] = Field(
        default=None,
        ge=0,
        le=3,
        description="Stops preference: 0 (any), 1 (nonstop only), 2 (1 stop or fewer), 3 (2 stops or fewer)"
    )
    currency: str = Field(
        default="INR",
        description="Currency code for pricing (e.g. 'INR', 'USD', 'EUR')"
    )
    max_price: Optional[float] = Field(
        default=None,
        description="Optional maximum total price filter"
    )
    sort_by: Optional[str] = Field(
        default="price",
        description="Sort order: 'price', 'duration', 'departure_time'"
    )
