"""
Google Places API service layer.

Mirrors the logic in ../places.py (the reference implementation) but uses
async httpx for non-blocking I/O and fetches photo URLs concurrently.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & Cache
# ---------------------------------------------------------------------------

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{resource_name}/media"

FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.googleMapsUri,"
    "places.photos,"
    "places.types"
)

MAX_PHOTO_WIDTH_PX = 800
REQUEST_TIMEOUT = 30  # seconds
CACHE_TTL_SECS = 86400 * 7  # 7 days

_redis_client = None
_in_memory_cache: dict[str, tuple[float, list[dict]]] = {}
_http_client: Optional[httpx.AsyncClient] = None


def _get_redis():
    global _redis_client
    redis_url = os.getenv("REDIS_URL")
    if redis_url and _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=2.0)
        except Exception as e:
            logger.warning("Redis not available in tourism-service (%s), using in-memory cache", e)
            _redis_client = False
    return _redis_client if _redis_client is not False else None


async def _cache_get(key: str) -> Optional[list[dict]]:
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


async def _cache_set(key: str, data: list[dict], ttl: int = CACHE_TTL_SECS):
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
# Helpers
# ---------------------------------------------------------------------------

def _api_key() -> str:
    """Return the Google Maps API key from the environment."""
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. "
            "Add it to the .env file in tourism_service/."
        )
    return key


async def _fetch_photo_url(
    client: httpx.AsyncClient,
    photo_resource_name: str,
    api_key: str,
) -> Optional[str]:
    """
    Convert a Google photo resource name into an actual image URL.

    Equivalent to get_photo_url() in places.py but async.
    Uses skipHttpRedirect=true so the API returns the URL as JSON
    rather than issuing a redirect — giving us a stable URL we can
    hand directly to the frontend as <img src="...">.
    """
    url = PHOTO_MEDIA_URL.format(resource_name=photo_resource_name)
    params = {
        "key": api_key,
        "maxWidthPx": MAX_PHOTO_WIDTH_PX,
        "skipHttpRedirect": "true",
    }

    try:
        response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            return data.get("photoUri")
    except httpx.RequestError:
        pass  # silently return None — image is optional

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_tourist_attractions(
    city_name: str,
    max_results: int = 10,
) -> list[dict]:
    """
    Search Google Places for tourist attractions in *city_name* and
    return a list of attraction dicts ready to be consumed by the
    Pydantic response model.

    Results are cached (Redis / in-memory) to prevent expensive Google billing.
    Photo URLs are resolved concurrently to keep total latency low.
    """
    cache_key = f"places:{city_name.strip().lower()}:{max_results}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        logger.info("Cache HIT for tourist attractions: %s", cache_key)
        return cached

    api_key = _api_key()

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    payload = {
        "textQuery": f"tourist attractions in {city_name}",
        "maxResultCount": min(max_results, 20),
    }

    client = await _get_http_client()

    # 1. Text search
    try:
        search_response = await client.post(
            SEARCH_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Google Places search request failed: {exc}"
        ) from exc

    if search_response.status_code != 200:
        raise RuntimeError(
            f"Google Places API error {search_response.status_code}: "
            f"{search_response.text}"
        )

    places_data = search_response.json().get("places", [])

    # 2. Resolve photo resource names → actual URLs concurrently
    photo_tasks = []
    for place in places_data:
        photos = place.get("photos", [])
        resource_name = photos[0].get("name") if photos else None
        if resource_name:
            photo_tasks.append(
                _fetch_photo_url(client, resource_name, api_key)
            )
        else:
            photo_tasks.append(_noop())

    photo_urls: list[Optional[str]] = await asyncio.gather(*photo_tasks)

    # 3. Build result list
    results: list[dict] = []

    for place, image_url in zip(places_data, photo_urls):
        location = place.get("location", {})

        attraction = {
            "name": place.get("displayName", {}).get("text", "N/A"),
            "address": place.get("formattedAddress", "N/A"),
            "rating": place.get("rating"),
            "review_count": place.get("userRatingCount", 0),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "google_maps_url": place.get("googleMapsUri"),
            "image_url": image_url,
            "types": place.get("types", []),
        }

        results.append(attraction)

    # Cache successful results
    if results:
        await _cache_set(cache_key, results)

    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _noop() -> None:
    """Awaitable that resolves immediately to None."""
    return None
