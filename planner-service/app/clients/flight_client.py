"""
Concrete Flight client — calls the standalone Flight Service.

Endpoint:
    POST {FLIGHT_SERVICE_URL}/flights/search
    Payload: { origin, destination, outbound_date, return_date, travelers, travel_class, currency }

Response shape (from flight-service):
    {
        "success": bool,
        "data": {
            "origin": str,
            "destination": str,
            "total_flights": int,
            "flights": [
                {
                    "flight_id", "airline", "airline_logo", "flight_number",
                    "departure_airport": {"id", "name", "time"},
                    "arrival_airport": {"id", "name", "time"},
                    "departure_time", "arrival_time",
                    "duration_minutes", "duration",
                    "stops", "price", "currency", "travel_class",
                    "booking_token", "departure_token", "is_best_flight"
                }
            ]
        }
    }
"""

import logging
from typing import Optional
import httpx

from app.config import settings
from app.interfaces.flight import FlightProvider
from app.schemas.context import FlightContext

logger = logging.getLogger(__name__)


class FlightClient(FlightProvider):
    """
    HTTP client for the standalone Flight Service microservice.
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
                    timeout=settings.http_timeout + 10.0  # Allow flight upstream enough time
                )
        except httpx.RequestError as exc:
            logger.warning("FlightClient network error: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "FlightClient returned %d: %s",
                response.status_code, response.text[:200]
            )
            return []

        try:
            data = response.json()
            flights_raw = data.get("data", {}).get("flights", [])
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

            logger.info("FlightClient retrieved %d normalized flights", len(result))
            return result

        except Exception as exc:
            logger.warning("FlightClient parse error: %s", exc)
            return []
