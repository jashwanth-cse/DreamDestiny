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
import json
import logging
import time
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.distanceMeters,routes.duration"
REQUEST_TIMEOUT = 15  # seconds
CACHE_TTL_SECS = 86400 * 14  # 14 days

TRAVEL_MODES = ["DRIVE", "TRANSIT"]

_redis_client = None
_in_memory_cache: dict[str, tuple[float, dict]] = {}
_http_client: Optional[httpx.AsyncClient] = None


def _get_redis():
    global _redis_client
    if settings.redis_url and _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2.0)
        except Exception as e:
            logger.warning("Redis not available in route-service (%s), using in-memory cache", e)
            _redis_client = False
    return _redis_client if _redis_client is not False else None


async def _cache_get(key: str) -> Optional[dict]:
    client = _get_redis()
    if client:
        try:
            val = await client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning("Redis get error for %s: %s", key, e)

    entry = _in_memory_cache.get(key)
    if entry:
        expires_at, data = entry
        if time.time() < expires_at:
            return data
        del _in_memory_cache[key]
    return None


async def _cache_set(key: str, data: dict, ttl: int = CACHE_TTL_SECS):
    client = _get_redis()
    if client:
        try:
            await client.set(key, json.dumps(data), ex=ttl)
            return
        except Exception as e:
            logger.warning("Redis set error for %s: %s", key, e)

    if len(_in_memory_cache) >= 500:
        oldest_k = next(iter(_in_memory_cache))
        del _in_memory_cache[oldest_k]
    _in_memory_cache[key] = (time.time() + ttl, data)


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    return _http_client


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
    Results are cached (Redis / in-memory) to prevent repeat billing.

    Returns a dict with:
        distance_km : from the DRIVE route (most reliable road distance)
        modes       : list of {mode, duration_minutes} for available modes

    Raises RuntimeError on configuration or fatal API errors.
    """
    cache_key = f"route:{origin.strip().lower()}:{destination.strip().lower()}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        logger.info("Cache HIT for route: %s", cache_key)
        return cached

    api_key = settings.google_maps_api_key
    if not api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. Add it to the .env file."
        )

    client = await _get_http_client()
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

    output = {
        "distance_km": distance_km,
        "modes": modes,
    }

    if distance_km is not None or modes:
        await _cache_set(cache_key, output)

    return output
