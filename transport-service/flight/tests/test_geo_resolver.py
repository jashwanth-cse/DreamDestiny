"""
Tests for GeoResolver — geo-coordinate based nearest airport discovery.

Test coverage:
  1. Haversine formula accuracy against known city-airport pairs.
  2. nearest_airport_from_coords — pure function, no network.
  3. GeoResolver.geocode — mocked Google Geocoding API.
  4. GeoResolver.nearest_airport — full pipeline, mocked geocoding.
  5. Cache hit — ensures geocoding API is not called twice for the same city.
  6. Graceful degradation — returns None on geocoding failure.
  7. AirportResolver.resolve_async — integration with geo fallback.
"""

from __future__ import annotations

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Haversine unit tests ──────────────────────────────────────────────────────

from app.resolver.geo_resolver import _haversine_km, nearest_airport_from_coords


def test_haversine_known_pair():
    """Coimbatore (11.017°N, 76.955°E) to CJB airport (11.03°N, 77.043°E) ≈ 9 km."""
    dist = _haversine_km(11.017, 76.955, 11.030, 77.043)
    assert 5 < dist < 15, f"Expected ~9 km, got {dist:.2f}"


def test_haversine_ooty_to_coimbatore_airport():
    """Ooty (11.41°N, 76.69°E) to CJB (11.03°N, 77.04°E) ≈ 60-90 km."""
    dist = _haversine_km(11.41, 76.69, 11.03, 77.04)
    assert 50 < dist < 120, f"Expected ~80 km, got {dist:.2f}"


def test_haversine_zero_distance():
    """Same point should return 0."""
    dist = _haversine_km(28.6139, 77.2090, 28.6139, 77.2090)
    assert dist == pytest.approx(0.0, abs=0.01)


def test_haversine_chennai_to_bengaluru():
    """Chennai to Bengaluru is roughly 290-310 km."""
    dist = _haversine_km(13.0827, 80.2707, 12.9716, 77.5946)
    assert 280 < dist < 340


# ── nearest_airport_from_coords unit tests ────────────────────────────────────

MOCK_AIRPORTS = {
    "CJB": {
        "iata": "CJB",
        "name": "Coimbatore International Airport",
        "city": "Coimbatore",
        "normalized_city": "coimbatore",
        "latitude": 11.030,
        "longitude": 77.043,
    },
    "MAA": {
        "iata": "MAA",
        "name": "Chennai International Airport",
        "city": "Chennai",
        "normalized_city": "chennai",
        "latitude": 12.990,
        "longitude": 80.169,
    },
    "IXM": {
        "iata": "IXM",
        "name": "Madurai Airport",
        "city": "Madurai",
        "normalized_city": "madurai",
        "latitude": 9.834,
        "longitude": 78.093,
    },
}


def test_nearest_airport_ooty():
    """Ooty should resolve to CJB (closest in mock set)."""
    result = nearest_airport_from_coords(11.41, 76.69, MOCK_AIRPORTS, max_radius_km=200)
    assert result is not None
    assert result["iata"] == "CJB"
    assert "distance_km" in result
    assert result["distance_km"] < 120


def test_nearest_airport_exceeds_radius():
    """With a tiny radius, no airport should be found."""
    result = nearest_airport_from_coords(11.41, 76.69, MOCK_AIRPORTS, max_radius_km=1)
    assert result is None


def test_nearest_airport_empty_dataset():
    """Empty dataset should return None."""
    result = nearest_airport_from_coords(11.41, 76.69, {}, max_radius_km=500)
    assert result is None


def test_nearest_airport_skips_missing_coords():
    """Airports without lat/lng should be skipped."""
    airports_no_coords = {
        "XXX": {"iata": "XXX", "name": "No Coords Airport"},
        "CJB": MOCK_AIRPORTS["CJB"],
    }
    result = nearest_airport_from_coords(11.41, 76.69, airports_no_coords, max_radius_km=200)
    assert result is not None
    assert result["iata"] == "CJB"


# ── GeoResolver unit tests (mocked HTTP) ──────────────────────────────────────

from app.resolver.geo_resolver import GeoResolver


@pytest.fixture
def geo_resolver():
    return GeoResolver(
        api_key="test_key",
        airports=MOCK_AIRPORTS,
        max_radius_km=500,
        cache_ttl_secs=3600,
    )


@pytest.mark.asyncio
async def test_geocode_success(geo_resolver):
    """Successful geocoding should return (lat, lng)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 11.41, "lng": 76.69}}}],
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await geo_resolver.geocode("Ooty")

    assert result == pytest.approx((11.41, 76.69), abs=0.001)


@pytest.mark.asyncio
async def test_geocode_no_results(geo_resolver):
    """Geocoding with no results should return None."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"status": "ZERO_RESULTS", "results": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await geo_resolver.geocode("NonExistentPlaceXYZ")

    assert result is None


@pytest.mark.asyncio
async def test_geocode_cache_hit(geo_resolver):
    """Second call with same city should use cache (HTTP called only once)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 11.41, "lng": 76.69}}}],
    }

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = mock_get
        mock_client_cls.return_value = mock_client

        await geo_resolver.geocode("Ooty")
        await geo_resolver.geocode("Ooty")   # second call — should hit cache

    assert call_count == 1, "Geocoding API should only be called once due to caching"


@pytest.mark.asyncio
async def test_nearest_airport_full_pipeline(geo_resolver):
    """Full pipeline: geocode 'Ooty' → find nearest airport (CJB)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 11.41, "lng": 76.69}}}],
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await geo_resolver.nearest_airport("Ooty")

    assert result is not None
    assert result["iata"] == "CJB"
    assert result["distance_km"] < 120
    assert result["resolution_method"] == "geo_nearest"


@pytest.mark.asyncio
async def test_nearest_airport_geocode_failure(geo_resolver):
    """If geocoding fails, nearest_airport should return None gracefully."""
    import httpx as _httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        result = await geo_resolver.nearest_airport("UnknownCity")

    assert result is None


# ── AirportResolver.resolve_async integration tests ──────────────────────────

from app.resolver.airport_resolver import AirportResolver
from app.exceptions import AirportNotFoundError


@pytest.mark.asyncio
async def test_resolve_async_direct_iata():
    """Direct IATA codes must resolve without touching the network."""
    iata, name, dist = await AirportResolver.resolve_async("MAA")
    assert iata == "MAA"
    assert "Chennai" in name
    assert dist == 0.0


@pytest.mark.asyncio
async def test_resolve_async_known_city():
    """Known city (in city index) resolves without geo fallback."""
    iata, name, dist = await AirportResolver.resolve_async("Chennai")
    assert iata == "MAA"
    assert dist == 0.0


@pytest.mark.asyncio
async def test_resolve_async_static_override():
    """Static override (Ooty → CJB) must resolve without network."""
    iata, name, dist = await AirportResolver.resolve_async("Ooty")
    assert iata == "CJB"
    assert dist == 0.0  # Static override, no geo call


@pytest.mark.asyncio
async def test_resolve_async_geo_fallback_used(monkeypatch):
    """
    For a city not in any index/override, geo fallback should be triggered.
    We patch the GeoResolver to avoid real network calls.
    """
    mock_match = {
        "iata": "XYZ",
        "name": "Test Airport",
        "distance_km": 42.5,
        "resolution_method": "geo_nearest",
    }

    mock_geo = AsyncMock()
    mock_geo.nearest_airport = AsyncMock(return_value=mock_match)

    # Reset class-level GeoResolver cache so our mock is picked up
    AirportResolver._geo_resolver = mock_geo

    try:
        iata, name, dist = await AirportResolver.resolve_async("SomeObscureTownNotInDatasetXYZ999")
        assert iata == "XYZ"
        assert dist == pytest.approx(42.5)
    finally:
        # Restore to None so other tests re-initialize properly
        AirportResolver._geo_resolver = None


@pytest.mark.asyncio
async def test_resolve_async_all_fail_raises(monkeypatch):
    """If static + city index + geo all fail, AirportNotFoundError is raised."""
    mock_geo = AsyncMock()
    mock_geo.nearest_airport = AsyncMock(return_value=None)
    AirportResolver._geo_resolver = mock_geo

    try:
        with pytest.raises(AirportNotFoundError):
            await AirportResolver.resolve_async("NotAPlaceEver99999")
    finally:
        AirportResolver._geo_resolver = None
