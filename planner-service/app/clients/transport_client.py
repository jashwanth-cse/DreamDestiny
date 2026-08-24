"""
Concrete Transport clients — Bus and Train.

Bus Service:
    GET {TRANSPORT_BUS_SERVICE_URL}/api/v1/buses/search
    Params: source, destination, journey_date, limit

    Response (from bus/app/models/response_models.py):
    {
        "success": bool,
        "data": {
            "buses": [
                {
                    "operator_name", "bus_type",
                    "departure_time", "arrival_time",
                    "duration_minutes", "duration",
                    "minimum_fare", "maximum_fare",
                    "available_seats", "amenities",
                    "rating", "boarding_point", "dropping_point",
                    ...
                }
            ]
        }
    }

Train Service:
    GET {TRANSPORT_TRAIN_SERVICE_URL}/api/v1/trains/search
    Params: from, to, date

    Response (from train/app/models/response_models.py):
    {
        "success": bool,
        "data": {
            "trains": [
                {
                    "train_number", "train_name", "train_type",
                    "from": {"code", "name"},
                    "to": {"code", "name"},
                    "departure_time", "arrival_time",
                    "duration_minutes", "duration",
                    "distance", "running_days",
                    "rating", "has_pantry", "lowest_fare",
                    "recommended_class", "classes"
                }
            ]
        }
    }
"""

import logging

import httpx

from app.config import settings
from app.interfaces.transport import BusProvider, TrainProvider
from app.schemas.context import (
    BusContext,
    TrainContext,
    TravelClassContext,
)

logger = logging.getLogger(__name__)


# ── Bus Client ────────────────────────────────────────────────────────────────

class BusClient(BusProvider):

    async def get_buses(
        self,
        source: str,
        destination: str,
        journey_date: str,
        limit: int = 10,
    ) -> list[BusContext]:
        url = f"{settings.transport_bus_service_url}/api/v1/buses/search"
        params = {
            "source": source,
            "destination": destination,
            "journey_date": journey_date,
            "limit": limit,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, timeout=settings.http_timeout
                )
        except httpx.RequestError as exc:
            logger.warning("BusClient network error: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "BusClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return []

        try:
            data = response.json()
            buses_raw = data.get("data", {}).get("buses", [])
            result = []
            for b in buses_raw:
                result.append(
                    BusContext(
                        operator_name=b.get("operator_name"),
                        bus_type=b.get("bus_type"),
                        departure_time=b.get("departure_time"),
                        arrival_time=b.get("arrival_time"),
                        duration_minutes=b.get("duration_minutes"),
                        duration=b.get("duration"),
                        minimum_fare=b.get("minimum_fare"),
                        maximum_fare=b.get("maximum_fare"),
                        available_seats=b.get("available_seats"),
                        amenities=b.get("amenities", []),
                        rating=b.get("rating"),
                        boarding_point=b.get("boarding_point"),
                        dropping_point=b.get("dropping_point"),
                    )
                )
            return result
        except Exception as exc:
            logger.warning("BusClient parse error: %s", exc)
            return []


# ── Train Client ──────────────────────────────────────────────────────────────

def _parse_travel_class(raw: dict) -> TravelClassContext:
    return TravelClassContext(
        travel_class=raw.get("travel_class", ""),
        fare=raw.get("fare", 0),
        availability=raw.get("availability", ""),
        bookable=raw.get("bookable", False),
    )


class TrainClient(TrainProvider):

    async def get_trains(
        self,
        source: str,
        destination: str,
        journey_date: str,
    ) -> list[TrainContext]:
        url = f"{settings.transport_train_service_url}/api/v1/trains/search"
        # Train service uses 'from' and 'to' as param names (aliased)
        params = {
            "from": source,
            "to": destination,
            "date": journey_date,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, timeout=settings.http_timeout
                )
        except httpx.RequestError as exc:
            logger.warning("TrainClient network error: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "TrainClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return []

        try:
            data = response.json()
            trains_raw = data.get("data", {}).get("trains", [])
            result = []
            for t in trains_raw:
                # Train model uses alias "from" for the from_ field
                rec_class_raw = t.get("recommended_class")
                result.append(
                    TrainContext(
                        train_number=t["train_number"],
                        train_name=t["train_name"],
                        train_type=t["train_type"],
                        departure_time=t["departure_time"],
                        arrival_time=t["arrival_time"],
                        duration_minutes=t["duration_minutes"],
                        duration=t["duration"],
                        distance_km=t.get("distance", 0),
                        lowest_fare=t.get("lowest_fare", 0),
                        rating=t.get("rating", 0.0),
                        has_pantry=t.get("has_pantry", False),
                        running_days=t.get("running_days", []),
                        recommended_class=(
                            _parse_travel_class(rec_class_raw)
                            if rec_class_raw else None
                        ),
                        classes=[
                            _parse_travel_class(c)
                            for c in t.get("classes", [])
                        ],
                    )
                )
            return result
        except Exception as exc:
            logger.warning("TrainClient parse error: %s", exc)
            return []
