"""
Airport and City Code Resolver.
===============================
Resolves city names, aliases, and 3-letter IATA codes into validated
IATA airport codes and official airport names using the preprocessed
global dataset `data/airports.json`.

Resolution priority (fast → slow):
  1. Direct 3-letter IATA code passthrough              (O(1), zero latency)
  2. Static alias / nearest-airport override table      (O(1), zero latency)
  3. In-memory city index (by_city)                     (O(1), zero latency)
  4. Substring / partial name match                     (O(n), ~1ms)
  5. [NEW] GeoResolver: geocode → Haversine nearest     (async HTTP, cached)

Performance Contract:
  - Loads airports.json once into memory at startup.
  - Steps 1–4 are synchronous, zero-network, and sub-millisecond.
  - Step 5 fires only when 1–4 all fail (city genuinely not in dataset).
  - Geocoding results are cached 24h in-process; repeated queries are free.
  - resolve_async() must be used to benefit from step 5.
  - resolve() (sync) only covers steps 1–4 for backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.exceptions import AirportNotFoundError

logger = logging.getLogger(__name__)

# ── Static overrides (kept as zero-latency fast-path) ────────────────────────
# These remain so cities like "Ooty" always resolve without a geocoding call.
# The geo fallback handles cities NOT in this table.
STATIC_NEAREST_AIRPORTS: Dict[str, Tuple[str, str]] = {
    "rajapalayam": ("IXM", "Madurai Airport (Nearest to Rajapalayam)"),
    "tirunelveli": ("TCR", "Tuticorin Airport (Nearest to Tirunelveli)"),
    "kanyakumari": ("TRV", "Thiruvananthapuram International Airport (Nearest to Kanyakumari)"),
    "ooty":        ("CJB", "Coimbatore International Airport (Nearest to Ooty)"),
    "kodaikanal":  ("IXM", "Madurai Airport (Nearest to Kodaikanal)"),
    "pondicherry": ("MAA", "Chennai International Airport (Nearest Major Airport)"),
}

IATA_RE = re.compile(r"^[A-Z]{3}$")


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _find_dataset_path() -> Optional[Path]:
    """Finds airports.json across common project paths."""
    env_path = os.environ.get("AIRPORTS_DATA_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "airports.json",
        Path("data/airports.json"),
        Path("../data/airports.json"),
        Path("../../data/airports.json"),
        Path("/app/data/airports.json"),
    ]

    for p in candidates:
        if p.exists():
            return p.resolve()
    return None


class AirportResolver:
    """
    In-memory airport resolver backed by preprocessed airports.json.
    Exposes both synchronous (resolve) and async (resolve_async) interfaces.
    """

    _airports: Dict[str, Dict[str, Any]] = {}
    _by_city: Dict[str, List[str]] = {}
    _by_country: Dict[str, List[str]] = {}
    _by_region: Dict[str, List[str]] = {}
    _initialized: bool = False

    # Lazily created GeoResolver — shared across all instances
    _geo_resolver: Optional["GeoResolver"] = None  # type: ignore[name-defined]  # noqa: F821

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        AirportResolver.load_dataset(dataset_path)

    # ── Dataset loading ───────────────────────────────────────────────────────

    @classmethod
    def load_dataset(cls, dataset_path: Optional[Path] = None) -> None:
        """Loads airports.json once into class-level memory."""
        if cls._initialized and not dataset_path:
            return

        target_path = dataset_path or _find_dataset_path()
        if not target_path or not target_path.exists():
            logger.warning("airports.json not found. Using static database fallback.")
            return

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cls._airports = data.get("airports", {})
            indexes = data.get("indexes", {})
            cls._by_city = indexes.get("by_city", {})
            cls._by_country = indexes.get("by_country", {})
            cls._by_region = indexes.get("by_region", {})
            cls._initialized = True
            logger.info(
                "AirportResolver loaded %d airports and %d indexed cities from %s",
                len(cls._airports),
                len(cls._by_city),
                target_path.name,
            )
        except Exception as exc:
            logger.error("Failed to load airports.json from %s: %s", target_path, exc)

    # ── GeoResolver lazy-init ─────────────────────────────────────────────────

    @classmethod
    def _get_geo_resolver(cls) -> Optional[Any]:
        """
        Lazily create and cache the GeoResolver singleton.
        Returns None if GOOGLE_MAPS_API_KEY is not configured (disables geo fallback).
        """
        if cls._geo_resolver is not None:
            return cls._geo_resolver

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            logger.debug(
                "GeoResolver disabled: GOOGLE_MAPS_API_KEY not set. "
                "Geo-based nearest airport fallback unavailable."
            )
            return None

        try:
            from app.resolver.geo_resolver import GeoResolver

            max_radius = float(os.environ.get("MAX_AIRPORT_RADIUS_KM", "500"))
            cache_ttl  = float(os.environ.get("GEOCODING_CACHE_TTL", "86400"))

            cls._geo_resolver = GeoResolver(
                api_key=api_key,
                airports=cls._airports,
                max_radius_km=max_radius,
                cache_ttl_secs=cache_ttl,
            )
            logger.info(
                "GeoResolver initialized (max_radius=%.0f km, cache_ttl=%.0fs)",
                max_radius, cache_ttl
            )
        except Exception as exc:
            logger.warning("Could not initialize GeoResolver: %s", exc)
            return None

        return cls._geo_resolver

    # ── Core fast-path resolution (synchronous, steps 1–4) ───────────────────

    @classmethod
    def _resolve_sync(cls, query: str) -> Optional[Tuple[str, str]]:
        """
        Steps 1–4 of resolution (synchronous, no network).
        Returns (iata_code, airport_name) or None if unresolvable without geo.
        """
        cleaned = query.strip()
        if not cleaned:
            raise AirportNotFoundError("Origin or destination query cannot be empty")

        upper = cleaned.upper()

        # Step 1: Direct 3-letter IATA code
        if IATA_RE.match(upper):
            if upper in cls._airports:
                return upper, cls._airports[upper]["name"]
            return upper, f"Airport ({upper})"

        normalized = _strip_accents(cleaned).lower()

        # Step 2: Static nearest-airport override (zero-latency fast-path)
        if normalized in STATIC_NEAREST_AIRPORTS:
            return STATIC_NEAREST_AIRPORTS[normalized]

        # Step 3: City index O(1) lookup
        if normalized in cls._by_city:
            iata_list = cls._by_city[normalized]
            if iata_list:
                primary_iata = iata_list[0]
                airport_name = cls._airports.get(primary_iata, {}).get(
                    "name", f"Airport ({primary_iata})"
                )
                return primary_iata, airport_name

        # Step 4: Substring / partial name match
        for iata, apt in cls._airports.items():
            apt_city = apt.get("normalized_city", "")
            apt_name = apt.get("name", "").lower()
            if normalized == apt_city or normalized in apt_name:
                return iata, apt.get("name", f"Airport ({iata})")

        return None  # Unresolvable via static methods

    # ── Synchronous resolve (backward compatible, steps 1–4 only) ────────────

    @classmethod
    def resolve(cls, query: str) -> Tuple[str, str]:
        """
        Synchronous resolve — steps 1–4 only.
        Raises AirportNotFoundError if unresolvable without geo fallback.

        Use resolve_async() for full geo-based resolution.
        """
        cls.load_dataset()
        result = cls._resolve_sync(query)
        if result is not None:
            return result

        raise AirportNotFoundError(
            f"Could not resolve '{query}' to an airport code. "
            "Please provide a recognized city name or 3-letter IATA code (e.g. 'Chennai' or 'MAA')."
        )

    # ── Async resolve with geo fallback (steps 1–5) ───────────────────────────

    @classmethod
    async def resolve_async(cls, query: str) -> Tuple[str, str, float]:
        """
        Full async resolution with geo-coordinate fallback.

        Resolution order:
          1–4. Synchronous fast-path (see _resolve_sync)
          5.   GeoResolver: geocode city → Haversine nearest airport

        Returns:
            (iata_code, airport_name, distance_km)
            distance_km == 0.0 for steps 1–4 (no spatial lookup required).

        Raises:
            AirportNotFoundError if all 5 steps fail.
        """
        cls.load_dataset()

        # Steps 1–4: synchronous fast-path
        result = cls._resolve_sync(query)
        if result is not None:
            iata, name = result
            return iata, name, 0.0

        # Step 5: Geo-coordinate based nearest airport
        geo = cls._get_geo_resolver()
        if geo is not None:
            match = await geo.nearest_airport(query)
            if match is not None:
                iata = match["iata"]
                name = match.get("name", f"Airport ({iata})")
                dist = match.get("distance_km", 0.0)
                logger.info(
                    "Resolved '%s' via geo-nearest → %s (%s, %.1f km)",
                    query, iata, name, dist
                )
                return iata, name, dist

        raise AirportNotFoundError(
            f"Could not resolve '{query}' to a nearby airport. "
            "The city could not be geocoded or no airport was found within the search radius. "
            "Please provide a recognized city name or 3-letter IATA code (e.g. 'Mumbai' or 'BOM')."
        )

    # ── Utility methods ───────────────────────────────────────────────────────

    @classmethod
    def get_airport(cls, iata: str) -> Optional[Dict[str, Any]]:
        """Retrieve full normalized airport record by IATA code."""
        cls.load_dataset()
        return cls._airports.get(iata.upper())

    @classmethod
    def find_by_country(cls, iso_country: str) -> List[Dict[str, Any]]:
        """Retrieve all airports in a given country code (e.g. 'IN', 'US')."""
        cls.load_dataset()
        codes = cls._by_country.get(iso_country.upper(), [])
        return [cls._airports[c] for c in codes if c in cls._airports]

    @classmethod
    def find_by_region(cls, iso_region: str) -> List[Dict[str, Any]]:
        """Retrieve all airports in a given region code (e.g. 'IN-TN', 'US-CA')."""
        cls.load_dataset()
        codes = cls._by_region.get(iso_region.upper(), [])
        return [cls._airports[c] for c in codes if c in cls._airports]
