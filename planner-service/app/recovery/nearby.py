"""Fresh, bounded Google Maps lookups for a traveler already at the destination."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import httpx

from app.config import settings
from app.recovery.models import RecoveryLocation

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
PLACE_FIELDS = ("places.id,places.displayName,places.formattedAddress,places.location,"
                "places.googleMapsUri,places.businessStatus,places.rating,places.userRatingCount")


@dataclass(frozen=True)
class ResolvedLocation:
    latitude: float
    longitude: float
    address: str


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(h))


class NearbySearchError(Exception):
    pass


class NearbyProvider:
    """Uses Places for identities and Routes for road travel times; no booking claims."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings.google_maps_api_key

    async def _geocode(self, client: httpx.AsyncClient, address: str,
                       precise: bool = False) -> ResolvedLocation:
        response = await client.get(GEOCODE_URL, params={"address": address, "key": self.api_key}, timeout=12)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            raise NearbySearchError("That location could not be resolved. Share a WhatsApp location pin or a more precise landmark.")
        result = data["results"][0]
        if precise and set(result.get("types") or []) & {"locality", "administrative_area_level_1"}:
            raise NearbySearchError("That location is too broad. Share a WhatsApp pin or a nearby bus stand, hotel, or street.")
        point = result["geometry"]["location"]
        return ResolvedLocation(float(point["lat"]), float(point["lng"]), result["formatted_address"])

    async def _places(self, client: httpx.AsyncClient, location: ResolvedLocation,
                      place_type: str) -> list[dict]:
        payload = {
            "includedTypes": [place_type], "maxResultCount": 10, "rankPreference": "DISTANCE",
            "locationRestriction": {"circle": {"center": {
                "latitude": location.latitude, "longitude": location.longitude}, "radius": 8000}},
        }
        response = await client.post(PLACES_URL, json=payload, headers={
            "X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": PLACE_FIELDS,
        }, timeout=15)
        response.raise_for_status()
        result = []
        for place in response.json().get("places", []):
            point = place.get("location") or {}
            if (not place.get("id") or not place.get("displayName", {}).get("text")
                    or point.get("latitude") is None or point.get("longitude") is None
                    or place.get("businessStatus") not in (None, "OPERATIONAL")):
                continue
            result.append({
                "id": place["id"], "name": place["displayName"]["text"],
                "address": place.get("formattedAddress", ""),
                "latitude": float(point["latitude"]), "longitude": float(point["longitude"]),
                "maps_url": place.get("googleMapsUri") or f"https://www.google.com/maps/place/?q=place_id:{place['id']}",
                "rating": place.get("rating"), "review_count": place.get("userRatingCount", 0),
            })
        return result

    async def _routes(self, client: httpx.AsyncClient, origin: ResolvedLocation,
                      places: list[dict]) -> list[dict]:
        if not places:
            return []
        def waypoint(lat, lon):
            return {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}}
        payload = {
            "origins": [waypoint(origin.latitude, origin.longitude)],
            "destinations": [waypoint(p["latitude"], p["longitude"]) for p in places],
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
        }
        response = await client.post(MATRIX_URL, json=payload, headers={
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "originIndex,destinationIndex,status,condition,distanceMeters,duration",
        }, timeout=18)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise NearbySearchError("Nearby route information is unavailable right now.")
        ranked = []
        for route in data:
            index = route.get("destinationIndex")
            if (route.get("condition") != "ROUTE_EXISTS" or not isinstance(index, int)
                    or index < 0 or index >= len(places) or route.get("distanceMeters") is None):
                continue
            try:
                minutes = max(1, round(float(str(route["duration"]).removesuffix("s")) / 60))
            except (ValueError, KeyError, TypeError):
                continue
            place = dict(places[index])
            place["distance_km"] = round(route["distanceMeters"] / 1000, 1)
            place["travel_minutes"] = minutes
            ranked.append(place)
        return sorted(ranked, key=lambda p: (p["travel_minutes"], p["distance_km"]))

    async def search(self, current: RecoveryLocation, destination: str):
        if not self.api_key:
            raise NearbySearchError("Google Maps is not configured.")
        try:
            async with httpx.AsyncClient() as client:
                city = await self._geocode(client, destination + ", India")
                if current.latitude is not None:
                    location = ResolvedLocation(current.latitude, current.longitude,
                                                current.address or "Shared WhatsApp location")
                else:
                    location = await self._geocode(client, f"{current.address}, {destination}, India", precise=True)
                if _km((location.latitude, location.longitude),
                       (city.latitude, city.longitude)) > 75:
                    raise NearbySearchError(
                        f"That pin appears outside {destination}. Share your current location in {destination}.")
                hotels, sights = await asyncio.gather(
                    self._places(client, location, "hotel"),
                    self._places(client, location, "tourist_attraction"),
                )
                routed = await self._routes(client, location, (hotels[:8] + sights[:8]))
                hotel_ids = {p["id"] for p in hotels}
                routed_hotels = [p for p in routed if p["id"] in hotel_ids]
                routed_sights = [p for p in routed if p["id"] not in hotel_ids]
                return location, routed_hotels, routed_sights
        except httpx.HTTPError as exc:
            raise NearbySearchError("Google Places or Routes is temporarily unavailable.") from exc
