"""
Google Routes API service layer.

Endpoint : POST https://routes.googleapis.com/directions/v2:computeRoutes
Docs     : https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes

We request DRIVE and TRANSIT concurrently using asyncio.gather.

Key response fields used:
    routes[0].distanceMeters          → distance in metres  → km
    routes[0].duration                → e.g. "3720s"        → minutes
    routes[0].travelAdvisory          → (unused for now)

The field mask controls exactly what Google bills and returns.
We request only distanceMeters + duration to keep costs minimal.
"""

import asyncio
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.distanceMeters,routes.duration"
REQUEST_TIMEOUT = 15  # seconds

# Travel modes we query. TRANSIT is attempted but may return no results
# for many city pairs — handled gracefully.
TRAVEL_MODES = ["DRIVE", "TRANSIT"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_duration_seconds(duration_str: Optional[str]) -> Optional[int]:
    """
    Convert Google's duration string (e.g. '3720s') to whole minutes.
    Returns None if the string is missing or malformed.
    """
    if not duration_str:
        return None
    try:
        seconds = int(duration_str.rstrip("s"))
        return round(seconds / 60)
    except (ValueError, AttributeError):
        return None


def _build_payload(origin: str, destination: str, travel_mode: str) -> dict:
    """
    Build the computeRoutes request body for a single travel mode.
    Uses address strings directly — no geocoding step needed.
    """
    return {
        "origin": {
            "address": origin,
        },
        "destination": {
            "address": destination,
        },
        "travelMode": travel_mode,
        # Use TRAFFIC_UNAWARE for driving — avoids real-time traffic billing.
        # Ignored for TRANSIT.
        "routingPreference": "TRAFFIC_UNAWARE" if travel_mode == "DRIVE" else None,
        "computeAlternativeRoutes": False,
        "languageCode": "en",
    }


async def _fetch_single_mode(
    client: httpx.AsyncClient,
    origin: str,
    destination: str,
    travel_mode: str,
    api_key: str,
) -> Optional[dict]:
    """
    Call computeRoutes for one travel mode.
    Returns a normalized dict or None if the mode is unavailable / errored.
    """
    payload = _build_payload(origin, destination, travel_mode)
    # Remove None values before sending
    payload = {k: v for k, v in payload.items() if v is not None}

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    try:
        response = await client.post(
            ROUTES_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.RequestError as exc:
        logger.warning("Routes API network error (%s): %s", travel_mode, exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "Routes API returned %d for mode %s: %s",
            response.status_code, travel_mode, response.text[:300],
        )
        return None

    data = response.json()
    routes = data.get("routes", [])

    if not routes:
        logger.info("No route returned by Google for mode=%s", travel_mode)
        return None

    route = routes[0]
    distance_meters: Optional[int] = route.get("distanceMeters")
    duration_str: Optional[str] = route.get("duration")

    duration_minutes = _parse_duration_seconds(duration_str)
    distance_km = round(distance_meters / 1000, 2) if distance_meters else None

    return {
        "mode": travel_mode.lower(),      # "drive" / "transit"
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_routes(origin: str, destination: str) -> dict:
    """
    Fetch DRIVE and TRANSIT routes concurrently from the Google Routes API.

    Returns a dict with:
        distance_km : from the DRIVE route (most reliable road distance)
        modes       : list of {mode, duration_minutes} for available modes

    Raises RuntimeError on configuration or fatal API errors.
    """
    api_key = settings.google_maps_api_key
    if not api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. Add it to the .env file."
        )

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[
                _fetch_single_mode(client, origin, destination, mode, api_key)
                for mode in TRAVEL_MODES
            ]
        )

    # results is [drive_result, transit_result] — each may be None
    drive_result, transit_result = results

    # distance_km comes from driving (authoritative road distance)
    distance_km = drive_result["distance_km"] if drive_result else None

    modes = []
    mode_label_map = {"drive": "driving", "transit": "transit"}

    for result in results:
        if result is None:
            continue
        modes.append(
            {
                "mode": mode_label_map.get(result["mode"], result["mode"]),
                "duration_minutes": result["duration_minutes"],
            }
        )

    return {
        "distance_km": distance_km,
        "modes": modes,
    }
