"""
Pydantic models for the Tourism Service response.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Attraction(BaseModel):
    """A single tourist attraction returned by the Google Places API."""

    name: str
    address: str
    rating: Optional[float] = None
    review_count: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    place_id: Optional[str] = None
    opening_hours: Optional[dict] = None
    business_status: Optional[str] = None


class TourismResponse(BaseModel):
    """Top-level response envelope for GET /tourism."""

    city: str
    count: int
    attractions: list[Attraction]
