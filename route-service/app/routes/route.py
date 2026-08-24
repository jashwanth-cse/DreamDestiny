"""
Route endpoint — GET /route
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.models import RouteMode, RouteResponse
from app.services.google_routes import fetch_routes

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/route",
    response_model=RouteResponse,
    summary="Get routes between two locations",
    responses={
        400: {"description": "Missing or invalid parameters"},
        503: {"description": "Google Routes API error"},
    },
)
async def get_route(
    origin: str = Query(
        ...,
        min_length=1,
        description="Origin city or address.",
        examples=["Chennai"],
    ),
    destination: str = Query(
        ...,
        min_length=1,
        description="Destination city or address.",
        examples=["Coimbatore"],
    ),
):
    """
    Returns verified distance and duration for **driving** and **transit**
    between *origin* and *destination* using the Google Routes API.

    - `distance_km` — road distance (from the driving route)
    - `routes[]` — one entry per available travel mode
    - `estimated_cost` — always `null` (not provided by Google Routes API)
    """
    try:
        data = await fetch_routes(origin=origin, destination=destination)
    except RuntimeError as exc:
        msg = str(exc)
        if "GOOGLE_MAPS_API_KEY is not set" in msg:
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=503, detail=msg)

    modes = [RouteMode(**m) for m in data["modes"]]

    return RouteResponse(
        origin=origin,
        destination=destination,
        distance_km=data["distance_km"],
        routes=modes,
    )
