"""
Concrete Flight client — calls the standalone Flight Service.

Endpoint:
    POST {FLIGHT_SERVICE_URL}/flights/search
    Payload: { origin, destination, outbound_date, return_date, travelers, travel_class, currency }

Response shape (from flight-service v2):
    {
        "success": bool,
        "data": {
            "origin": str,                           # Resolved IATA
            "origin_name": str,
            "origin_city": str,                      # Original queried city
            "origin_airport_distance_km": float|null, # null if city has own airport
            "destination": str,
            "destination_name": str,
            "destination_city": str,
            "destination_airport_distance_km": float|null,
            "flights": [ ... ]
        }
    }
"""

import logging
from typing import Optional, Tuple
import httpx

from app.config import settings
from app.interfaces.flight import FlightProvider
from app.schemas.context import FlightContext, FlightResolutionContext

logger = logging.getLogger(__name__)


class FlightClient(FlightProvider):
    """
    HTTP client for the standalone Flight Service microservice.
    Returns both the flight list and airport resolution metadata.
    """

    async def get_flights(
        self,
        origin: str,
        destination: str,
        outbound_date: str,
        return_date: Optional[str] = None,
        travelers: int = 1,
        travel_class: Optional[str] = "economy",
    ) -> list[FlightContext]:
        """Backward-compatible method — returns flight list only."""
        flights, _ = await self.get_flights_with_resolution(
            origin=origin,
            destination=destination,
            outbound_date=outbound_date,
            return_date=return_date,
            travelers=travelers,
            travel_class=travel_class,
        )
        return flights

    async def get_flights_with_resolution(
        self,
        origin: str,
        destination: str,
        outbound_date: str,
        return_date: Optional[str] = None,
        travelers: int = 1,
        travel_class: Optional[str] = "economy",
    ) -> Tuple[list[FlightContext], Optional[FlightResolutionContext]]:
        """
        Full method — returns (flights, FlightResolutionContext).
        FlightResolutionContext carries nearest-airport distances when
        geo-based resolution was used by the flight-service.
        """
        base_url = settings.flight_service_url or settings.transport_flight_service_url
        url = f"{base_url.rstrip('/')}/flights/search"

        payload = {
            "origin": origin,
            "destination": destination,
            "outbound_date": outbound_date,
            "return_date": return_date,
            "travelers": travelers,
            "travel_class": travel_class or "economy",
            "currency": "INR",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=settings.http_timeout + 10.0,
                )
        except httpx.RequestError as exc:
            logger.warning("FlightClient network error: %s", exc)
            return [], None

        if response.status_code != 200:
            logger.warning(
                "FlightClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return [], None

        try:
            body = response.json()
            data = body.get("data", {})
            flights_raw = data.get("flights", [])
            result: list[FlightContext] = []

            for f in flights_raw:
                dep_airport = f.get("departure_airport") or {}
                arr_airport = f.get("arrival_airport") or {}

                result.append(
                    FlightContext(
                        flight_id=f.get("flight_id", ""),
                        airline=f.get("airline"),
                        airline_logo=f.get("airline_logo"),
                        flight_number=f.get("flight_number"),
                        departure_airport_code=dep_airport.get("id", ""),
                        departure_airport_name=dep_airport.get("name"),
                        arrival_airport_code=arr_airport.get("id", ""),
                        arrival_airport_name=arr_airport.get("name"),
                        departure_time=f.get("departure_time"),
                        arrival_time=f.get("arrival_time"),
                        duration_minutes=f.get("duration_minutes"),
                        duration=f.get("duration"),
                        stops=f.get("stops", 0),
                        price=f.get("price"),
                        currency=f.get("currency", "INR"),
                        travel_class=f.get("travel_class"),
                        booking_token=f.get("booking_token"),
                        departure_token=f.get("departure_token"),
                        is_best_flight=f.get("is_best_flight", False),
                    )
                )

            # Extract airport resolution metadata (new in v2)
            origin_dist = data.get("origin_airport_distance_km")
            dest_dist   = data.get("destination_airport_distance_km")

            resolution: Optional[FlightResolutionContext] = None
            if origin_dist is not None or dest_dist is not None:
                resolution = FlightResolutionContext(
                    origin_city=data.get("origin_city") or origin,
                    origin_iata=data.get("origin"),
                    origin_airport_name=data.get("origin_name"),
                    origin_airport_distance_km=origin_dist,
                    destination_city=data.get("destination_city") or destination,
                    destination_iata=data.get("destination"),
                    destination_airport_name=data.get("destination_name"),
                    destination_airport_distance_km=dest_dist,
                )
                logger.info(
                    "FlightClient: geo-resolution used — "
                    "origin '%s' → %s (%.1f km), destination '%s' → %s (%.1f km)",
                    origin, data.get("origin"), origin_dist or 0.0,
                    destination, data.get("destination"), dest_dist or 0.0,
                )

            logger.info("FlightClient retrieved %d normalized flights", len(result))
            return result, resolution

        except Exception as exc:
            logger.warning("FlightClient parse error: %s", exc)
            return [], None
