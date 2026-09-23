"""
Flight Service layer.
Coordinates input resolution (AirportResolver) and provider execution (FlightProvider).
Stateless and thread-safe.
"""

import logging
from typing import Optional
from app.models.request_models import FlightSearchRequest
from app.models.response_models import FlightSearchResponse, FlightSearchData
from app.resolver.airport_resolver import AirportResolver
from app.provider.base import FlightProvider
from app.provider.serpapi_provider import SerpApiFlightProvider
from app.utils import normalize_flight_date

logger = logging.getLogger(__name__)


class FlightService:
    """
    Core service class for flight searches.
    Loosely coupled with FlightProvider via dependency injection.
    """

    def __init__(self, provider: Optional[FlightProvider] = None):
        self.provider = provider or SerpApiFlightProvider()
        self.resolver = AirportResolver()

    async def search(self, request: FlightSearchRequest) -> FlightSearchResponse:
        """
        Main entry point for flight searches.
        1. Resolves origin and destination to IATA codes
        2. Calls provider to search flights
        3. Wraps normalized response
        """
        # Step 1: Resolve origin & destination to valid 3-letter IATA codes
        origin_code, origin_name = self.resolver.resolve(request.origin)
        dest_code, dest_name = self.resolver.resolve(request.destination)

        logger.info(
            "Searching flights: %s (%s) → %s (%s) on %s",
            origin_name, origin_code, dest_name, dest_code, request.outbound_date
        )

        # Step 2: Execute search via provider
        flights, best_count, other_count, trip_type = await self.provider.search_flights(
            origin_code=origin_code,
            destination_code=dest_code,
            request=request
        )

        norm_outbound = normalize_flight_date(request.outbound_date)
        norm_return = normalize_flight_date(request.return_date) if request.return_date else None

        search_data = FlightSearchData(
            origin=origin_code,
            origin_name=origin_name,
            destination=dest_code,
            destination_name=dest_name,
            outbound_date=norm_outbound,
            return_date=norm_return,
            trip_type=trip_type,
            total_flights=len(flights),
            best_flights_count=best_count,
            other_flights_count=other_count,
            flights=flights
        )

        return FlightSearchResponse(
            success=True,
            message=f"Found {len(flights)} flight options",
            data=search_data
        )
