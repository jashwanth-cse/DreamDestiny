"""
Pydantic models for the Route Service request and response.
"""

from typing import Optional
from pydantic import BaseModel, Field


class RouteMode(BaseModel):
    """
    A single travel mode option between origin and destination.

    Fields sourced from Google Routes API computeRoutes response:
        routes[0].distanceMeters  → used to populate distance_km on parent
        routes[0].duration        → e.g. "3600s" parsed to duration_minutes
        travelMode                → mode label (driving / transit)
    """

    mode: str = Field(..., description="Travel mode: driving or transit.")
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Journey duration in minutes from Google Routes API.",
    )


class RouteResponse(BaseModel):
    """
    Top-level response envelope for GET /route.

    distance_km is taken from the driving route's distanceMeters
    (most reliable for road distance). If driving is unavailable, null.
    """

    origin: str
    destination: str
    distance_km: Optional[float] = Field(
        default=None,
        description="Road distance in km (from DRIVE route distanceMeters).",
    )
    routes: list[RouteMode] = Field(
        default_factory=list,
        description="Available travel mode options returned by Google Routes API.",
    )
