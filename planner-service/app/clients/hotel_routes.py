"""Bounded Google Routes matrix and geocoding for hotel selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import ceil

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@dataclass(frozen=True)
class RoadRoute:
    minutes: int
    distance_km: float


class HotelRoutesClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings.google_maps_api_key

    async def matrix(self, origins: list[tuple[float, float]],
                     destinations: list[tuple[float, float]]) -> dict[tuple[int, int], RoadRoute]:
        if not self.api_key or not origins or not destinations:
            return {}
        if len(origins) * len(destinations) > 200:
            raise ValueError("Hotel route matrix exceeds the bounded 200-element budget")
        def waypoint(point: tuple[float, float]) -> dict:
            return {"waypoint": {"location": {"latLng": {
                "latitude": point[0], "longitude": point[1]}}}}
        payload = {"origins": [waypoint(point) for point in origins],
                   "destinations": [waypoint(point) for point in destinations],
                   "travelMode": "DRIVE", "routingPreference": "TRAFFIC_UNAWARE"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(22.0, connect=5.0)) as client:
                response = await client.post(MATRIX_URL, json=payload, headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "originIndex,destinationIndex,status,condition,distanceMeters,duration"})
                response.raise_for_status()
                rows = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Hotel Routes matrix unavailable: %s", type(exc).__name__)
            return {}
        if not isinstance(rows, list):
            return {}
        result = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("condition") != "ROUTE_EXISTS":
                continue
            i, j = row.get("originIndex"), row.get("destinationIndex")
            if (not isinstance(i, int) or not isinstance(j, int) or i < 0 or j < 0 or
                    i >= len(origins) or j >= len(destinations)):
                continue
            try:
                seconds = float(str(row["duration"]).removesuffix("s"))
                distance = float(row["distanceMeters"])
            except (KeyError, ValueError, TypeError):
                continue
            if seconds < 0 or distance < 0:
                continue
            result[(i, j)] = RoadRoute(max(1, ceil(seconds / 60)), round(distance / 1000, 1))
        return result

    async def geocode_stop(self, stop: str, city: str) -> tuple[float, float] | None:
        if not self.api_key or not stop or stop.casefold().strip() == city.casefold().strip():
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
                response = await client.get(GEOCODE_URL, params={
                    "address": f"{stop}, {city}, India", "key": self.api_key})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if data.get("status") != "OK" or not data.get("results"):
            return None
        result = data["results"][0]
        if set(result.get("types") or []) & {"locality", "administrative_area_level_1", "country"}:
            return None
        point = (result.get("geometry") or {}).get("location") or {}
        try:
            return float(point["lat"]), float(point["lng"])
        except (KeyError, TypeError, ValueError):
            return None
