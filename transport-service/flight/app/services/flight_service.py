"""
Flight Service layer.
Coordinates input resolution (AirportResolver) and provider execution (FlightProvider).
Stateless and thread-safe.

Geo-Resolution Change (v2):
  Uses AirportResolver.resolve_async() which adds a 5th step — Google Geocoding
  API + Haversine nearest-airport scan — so any city in the world resolves to
  its nearest commercial airport even if it has no airport of its own.
  The resolved distance_km is included in the response for transparency.
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

        Flow:
          1. Resolve origin & destination to IATA codes using full async pipeline
             (direct code → alias → city index → substring → geo-nearest).
          2. Log nearest-airport distances when geo resolution was used.
          3. Call provider to search flights.
          4. Return normalized response including resolved airport metadata.
        """
        # Step 1: Resolve origin & destination (async, geo-fallback enabled)
        origin_code, origin_name, origin_dist_km = await AirportResolver.resolve_async(
            request.origin
        )
        dest_code, dest_name, dest_dist_km = await AirportResolver.resolve_async(
            request.destination
        )

        # Step 2: Warn if geo resolution was used (distance > 0 means geo was needed)
        if origin_dist_km > 0:
            logger.info(
                "Origin '%s' has no direct airport. Nearest: %s (%s) — %.1f km away.",
                request.origin, origin_code, origin_name, origin_dist_km,
            )
        if dest_dist_km > 0:
            logger.info(
                "Destination '%s' has no direct airport. Nearest: %s (%s) — %.1f km away.",
                request.destination, dest_code, dest_name, dest_dist_km,
            )

        logger.info(
            "Searching flights: %s (%s) → %s (%s) on %s",
            origin_name, origin_code, dest_name, dest_code, request.outbound_date,
        )

        # Step 3: Execute search via provider
        flights, best_count, other_count, trip_type = await self.provider.search_flights(
            origin_code=origin_code,
            destination_code=dest_code,
            request=request,
        )

        norm_outbound = normalize_flight_date(request.outbound_date)
        norm_return = normalize_flight_date(request.return_date) if request.return_date else None

        search_data = FlightSearchData(
            origin=origin_code,
            origin_name=origin_name,
            origin_city=request.origin,
            origin_airport_distance_km=round(origin_dist_km, 2) if origin_dist_km > 0 else None,
            destination=dest_code,
            destination_name=dest_name,
            destination_city=request.destination,
            destination_airport_distance_km=round(dest_dist_km, 2) if dest_dist_km > 0 else None,
            outbound_date=norm_outbound,
            return_date=norm_return,
            trip_type=trip_type,
            total_flights=len(flights),
            best_flights_count=best_count,
            other_flights_count=other_count,
            flights=flights,
        )

        # Build user-facing message
        msg_parts = [f"Found {len(flights)} flight option(s)"]
        if origin_dist_km > 0:
            msg_parts.append(
                f"nearest airport to {request.origin}: {origin_name} ({origin_code}, "
                f"{origin_dist_km:.0f} km away)"
            )
        if dest_dist_km > 0:
            msg_parts.append(
                f"nearest airport to {request.destination}: {dest_name} ({dest_code}, "
                f"{dest_dist_km:.0f} km away)"
            )

        return FlightSearchResponse(
            success=True,
            message=". ".join(msg_parts),
            data=search_data,
        )
