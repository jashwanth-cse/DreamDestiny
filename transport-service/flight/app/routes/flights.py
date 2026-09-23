"""
Flight Search API Routes.
Exposes POST /flights/search and POST /api/v1/flights/search.
"""

import logging
from fastapi import APIRouter, Depends, status
from app.models.request_models import FlightSearchRequest
from app.models.response_models import FlightSearchResponse, ErrorResponse
from app.services.flight_service import FlightService

logger = logging.getLogger(__name__)

router = APIRouter()

# Default singleton instance
_flight_service = FlightService()


def get_flight_service() -> FlightService:
    return _flight_service


@router.post(
    "/flights/search",
    response_model=FlightSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search Flights",
    description="Search for one-way or round-trip flights using SerpApi Google Flights API. "
                "Accepts city names (e.g. 'Chennai') or 3-letter IATA codes (e.g. 'MAA').",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid flight request parameters"},
        404: {"model": ErrorResponse, "description": "Airport or city not found"},
        500: {"model": ErrorResponse, "description": "Internal server or provider error"},
        504: {"model": ErrorResponse, "description": "Upstream flight provider timeout"},
    }
)
async def search_flights(
    request: FlightSearchRequest,
    service: FlightService = Depends(get_flight_service)
) -> FlightSearchResponse:
    """
    Search flights endpoint.
    """
    logger.info(
        "Received flight search request: %s → %s on %s",
        request.origin, request.destination, request.outbound_date
    )
    return await service.search(request)


# Versioned route alias for API consistency
@router.post(
    "/api/v1/flights/search",
    response_model=FlightSearchResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False
)
async def search_flights_v1_alias(
    request: FlightSearchRequest,
    service: FlightService = Depends(get_flight_service)
) -> FlightSearchResponse:
    return await service.search(request)
