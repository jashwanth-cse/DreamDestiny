"""
SerpApi Google Flights Provider Implementation.

Interacts with SerpApi (engine=google_flights) using async httpx.
Parses, cleans, and normalizes raw SerpApi JSON payloads into our Pydantic domain models.
Isolates all SerpApi-specific JSON details from the rest of the application.
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
import httpx

from app.config import settings
from app.exceptions import (
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderAPIError,
)
from app.models.request_models import FlightSearchRequest
from app.models.response_models import (
    Flight,
    FlightSegment,
    AirportInfo,
    LayoverInfo,
    CarbonEmissions,
)
from app.provider.base import FlightProvider
from app.utils import (
    normalize_flight_date,
    map_travel_class,
    minutes_to_duration,
    generate_flight_id,
)

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


class SerpApiFlightProvider(FlightProvider):
    """
    Concrete FlightProvider using SerpApi Google Flights API.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.serpapi_api_key

    def _build_params(
        self,
        origin_code: str,
        destination_code: str,
        request: FlightSearchRequest
    ) -> Dict[str, Any]:
        """Builds SerpApi query parameters."""
        if not self.api_key:
            raise ProviderAuthenticationError(
                "SERPAPI_API_KEY is not set. Please provide it in .env or the request."
            )

        norm_outbound = normalize_flight_date(request.outbound_date)
        norm_return = normalize_flight_date(request.return_date) if request.return_date else None

        # Type: 1 = Round trip (requires return_date), 2 = One way
        is_round_trip = bool(norm_return)
        trip_type = "1" if is_round_trip else "2"

        travel_class_code = map_travel_class(request.travel_class)
        adults = request.adults if request.adults is not None else request.travelers

        params: Dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": origin_code.upper(),
            "arrival_id": destination_code.upper(),
            "outbound_date": norm_outbound,
            "type": trip_type,
            "travel_class": str(travel_class_code),
            "adults": str(adults),
            "currency": request.currency.upper(),
            "hl": "en",
            "api_key": self.api_key,
        }

        if is_round_trip and norm_return:
            params["return_date"] = norm_return

        if request.children is not None and request.children > 0:
            params["children"] = str(request.children)

        # Stops filter: 0 = any, 1 = nonstop, 2 = 1 stop or fewer, 3 = 2 stops or fewer
        if request.stops is not None and request.stops in (1, 2, 3):
            params["stops"] = str(request.stops)

        return params

    def _parse_airport(self, raw_airport: Optional[Dict[str, Any]]) -> AirportInfo:
        """Parses raw airport object into AirportInfo schema."""
        if not raw_airport:
            return AirportInfo(id="UNK", name=None, time=None)

        return AirportInfo(
            id=str(raw_airport.get("id") or "UNK"),
            name=raw_airport.get("name"),
            time=raw_airport.get("time")
        )

    def _parse_segment(self, raw_seg: Dict[str, Any]) -> FlightSegment:
        """Parses individual flight segment / leg."""
        dep_airport = self._parse_airport(raw_seg.get("departure_airport"))
        arr_airport = self._parse_airport(raw_seg.get("arrival_airport"))

        return FlightSegment(
            airline=raw_seg.get("airline"),
            airline_logo=raw_seg.get("airline_logo"),
            flight_number=raw_seg.get("flight_number"),
            airplane=raw_seg.get("airplane"),
            travel_class=raw_seg.get("travel_class"),
            legroom=raw_seg.get("legroom"),
            departure_airport=dep_airport,
            arrival_airport=arr_airport,
            duration_minutes=raw_seg.get("duration"),
            extensions=raw_seg.get("extensions") or []
        )

    def _parse_layovers(self, raw_layovers: Optional[List[Dict[str, Any]]]) -> List[LayoverInfo]:
        """Parses layover array."""
        if not raw_layovers:
            return []

        result = []
        for lay in raw_layovers:
            if isinstance(lay, dict):
                result.append(
                    LayoverInfo(
                        name=lay.get("name"),
                        id=lay.get("id"),
                        duration_minutes=lay.get("duration")
                    )
                )
        return result

    def _parse_carbon(self, raw_carbon: Optional[Dict[str, Any]]) -> Optional[CarbonEmissions]:
        """Parses emissions data."""
        if not raw_carbon or not isinstance(raw_carbon, dict):
            return None

        return CarbonEmissions(
            this_flight_grams=raw_carbon.get("this_flight"),
            typical_for_route_grams=raw_carbon.get("typical_for_this_route"),
            difference_percent=raw_carbon.get("difference_percent")
        )

    def _normalize_flight(
        self,
        raw_flight: Dict[str, Any],
        is_best: bool,
        currency: str
    ) -> Flight:
        """
        Normalizes a single raw flight dict from SerpApi into our clean Flight model.
        Never invents missing values; uses None.
        """
        segments_raw = raw_flight.get("flights") or []
        segments = [self._parse_segment(seg) for seg in segments_raw]

        if segments:
            dep_airport = segments[0].departure_airport
            arr_airport = segments[-1].arrival_airport
            dep_time = dep_airport.time
            arr_time = arr_airport.time
            primary_airline = segments[0].airline
            airline_logo = raw_flight.get("airline_logo") or segments[0].airline_logo
            flight_numbers = [seg.flight_number for seg in segments if seg.flight_number]
            flight_number_str = ", ".join(flight_numbers) if flight_numbers else segments[0].flight_number
            travel_class = segments[0].travel_class
            stops = max(0, len(segments) - 1)
        else:
            dep_airport = AirportInfo(id="UNK", name=None, time=None)
            arr_airport = AirportInfo(id="UNK", name=None, time=None)
            dep_time = None
            arr_time = None
            primary_airline = None
            airline_logo = raw_flight.get("airline_logo")
            flight_number_str = None
            travel_class = None
            stops = 0

        duration_mins = raw_flight.get("total_duration")
        if duration_mins is None and segments:
            duration_mins = sum(seg.duration_minutes or 0 for seg in segments)

        price_val = raw_flight.get("price")
        price = float(price_val) if price_val is not None else None

        booking_token = raw_flight.get("booking_token")
        departure_token = raw_flight.get("departure_token")

        flight_id = generate_flight_id(
            booking_token=booking_token,
            flight_number=flight_number_str,
            departure_time=dep_time,
            arrival_time=arr_time,
            airline=primary_airline
        )

        return Flight(
            flight_id=flight_id,
            airline=primary_airline,
            airline_logo=airline_logo,
            flight_number=flight_number_str,
            departure_airport=dep_airport,
            arrival_airport=arr_airport,
            departure_time=dep_time,
            arrival_time=arr_time,
            duration_minutes=duration_mins,
            duration=minutes_to_duration(duration_mins),
            stops=stops,
            price=price,
            currency=currency,
            travel_class=travel_class,
            booking_token=booking_token,
            departure_token=departure_token,
            is_best_flight=is_best,
            segments=segments,
            layovers=self._parse_layovers(raw_flight.get("layovers")),
            carbon_emissions=self._parse_carbon(raw_flight.get("carbon_emissions"))
        )

    async def search_flights(
        self,
        origin_code: str,
        destination_code: str,
        request: FlightSearchRequest
    ) -> Tuple[List[Flight], int, int, str]:
        """
        Calls SerpApi Google Flights API, combines best_flights and other_flights,
        and returns normalized Pydantic domain models.
        """
        params = self._build_params(origin_code, destination_code, request)
        trip_type = "round_trip" if params.get("type") == "1" else "one_way"

        logger.info(
            "Calling SerpApi Google Flights: origin=%s, dest=%s, date=%s, type=%s",
            origin_code, destination_code, params.get("outbound_date"), trip_type
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    SERPAPI_URL,
                    params=params,
                    timeout=settings.http_timeout
                )
        except httpx.TimeoutException as exc:
            logger.error("SerpApi request timed out: %s", exc)
            raise ProviderTimeoutError(f"SerpApi Google Flights request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            logger.error("SerpApi network request failed: %s", exc)
            raise ProviderAPIError(f"SerpApi connection failure: {exc}") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderAuthenticationError("Invalid or unauthorized SERPAPI_API_KEY")

        if response.status_code != 200:
            err_msg = f"SerpApi returned HTTP {response.status_code}: {response.text[:300]}"
            logger.error(err_msg)
            raise ProviderAPIError(err_msg)

        data = response.json()

        # Check for provider-level error message in response body
        if "error" in data:
            raise ProviderAPIError(f"SerpApi Google Flights error: {data['error']}")

        # ── Combine best_flights and other_flights ────────────────────────────
        raw_best = data.get("best_flights") or []
        raw_other = data.get("other_flights") or []

        normalized_best = [
            self._normalize_flight(f, is_best=True, currency=request.currency)
            for f in raw_best
        ]
        normalized_other = [
            self._normalize_flight(f, is_best=False, currency=request.currency)
            for f in raw_other
        ]

        combined = normalized_best + normalized_other

        # Optional max price filter
        if request.max_price is not None:
            combined = [f for f in combined if f.price is not None and f.price <= request.max_price]

        # Optional sort
        if request.sort_by == "price":
            combined.sort(key=lambda x: (x.price is None, x.price or 0))
        elif request.sort_by == "duration":
            combined.sort(key=lambda x: (x.duration_minutes is None, x.duration_minutes or 0))
        elif request.sort_by == "departure_time":
            combined.sort(key=lambda x: x.departure_time or "")

        return combined, len(raw_best), len(raw_other), trip_type
