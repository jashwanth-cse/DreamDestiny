"""Supplement a general sightseeing search with requested place categories."""

from __future__ import annotations

import logging
import time
from typing import Callable

import httpx

from app.config import settings
from app.schemas.context import AttractionContext, TripContext

logger = logging.getLogger(__name__)
URL = "https://places.googleapis.com/v1/places:searchText"
MASK = ("places.id,places.displayName,places.formattedAddress,places.location,"
        "places.rating,places.userRatingCount,places.googleMapsUri,places.types,"
        "places.regularOpeningHours,places.businessStatus")


class InterestPlacesClient:
    def __init__(self, trace: Callable | None = None):
        self.trace = trace

    async def add_requested_places(self, context: TripContext) -> None:
        interests = {value.casefold() for value in context.trip.preferences.activities.interests}
        if "museums" not in interests or not settings.google_maps_api_key:
            return
        city = context.trip.destination
        payload = {"textQuery": f"museums in {city}, India", "maxResultCount": 5}
        started = time.perf_counter()
        if self.trace:
            self.trace("tool_call", provider="google_places_interest", request=payload)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=5.0)) as client:
                response = await client.post(URL, json=payload, headers={"X-Goog-Api-Key": settings.google_maps_api_key,
                            "X-Goog-FieldMask": MASK})
                response.raise_for_status()
                results = response.json().get("places") or []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Requested museum Places lookup unavailable: %s", type(exc).__name__)
            if self.trace:
                self.trace("tool_error", provider="google_places_interest",
                           latency_ms=round((time.perf_counter() - started) * 1000), error=type(exc).__name__)
            return
        if self.trace:
            self.trace("tool_result", provider="google_places_interest",
                       latency_ms=round((time.perf_counter() - started) * 1000), output=results)
        existing = {place.name.casefold() for place in context.attractions}
        for record in results:
            name = ((record.get("displayName") or {}).get("text") or "").strip()
            address = record.get("formattedAddress") or ""
            point = record.get("location") or {}
            if (not name or "museum" not in name.casefold() or
                    city.casefold() not in address.casefold() or
                    record.get("businessStatus") in {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"} or
                    name.casefold() in existing or not record.get("id")):
                continue
            context.attractions.append(AttractionContext(
                name=name, address=address, rating=record.get("rating"),
                review_count=record.get("userRatingCount") or 0,
                latitude=point.get("latitude"), longitude=point.get("longitude"),
                google_maps_url=record.get("googleMapsUri"),
                types=record.get("types") or [], place_id=record["id"],
                opening_hours=record.get("regularOpeningHours"),
                business_status=record.get("businessStatus")))
            existing.add(name.casefold())
