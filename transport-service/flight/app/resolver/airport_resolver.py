"""
Airport and City Code Resolver.
===============================
Resolves city names, aliases, and 3-letter IATA codes into validated
IATA airport codes and official airport names using the preprocessed
global dataset `data/airports.json`.

Performance Contract:
  - Loads generated JSON once into memory at startup.
  - O(1) dictionary lookups for IATA codes and city names.
  - Never parses raw CSV files at runtime.
  - Backward-compatible with static nearest-airport overrides (e.g. Rajapalayam -> IXM).
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

# Fallback nearest-airport mappings for towns without their own airport
STATIC_NEAREST_AIRPORTS: Dict[str, Tuple[str, str]] = {
    "rajapalayam": ("IXM", "Madurai Airport (Nearest to Rajapalayam)"),
    "tirunelveli": ("TCR", "Tuticorin Airport (Nearest to Tirunelveli)"),
    "kanyakumari": ("TRV", "Thiruvananthapuram International Airport (Nearest to Kanyakumari)"),
    "ooty": ("CJB", "Coimbatore International Airport (Nearest to Ooty)"),
    "kodaikanal": ("IXM", "Madurai Airport (Nearest to Kodaikanal)"),
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
    """

    _airports: Dict[str, Dict[str, Any]] = {}
    _by_city: Dict[str, List[str]] = {}
    _by_country: Dict[str, List[str]] = {}
    _by_region: Dict[str, List[str]] = {}
    _initialized: bool = False

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        AirportResolver.load_dataset(dataset_path)

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

    @classmethod
    def resolve(cls, query: str) -> Tuple[str, str]:
        """
        Resolves query (IATA code, city name, alias) to (iata_code, airport_name).
        Raises AirportNotFoundError if query cannot be resolved.
        """
        cls.load_dataset()

        cleaned = query.strip()
        if not cleaned:
            raise AirportNotFoundError("Origin or destination query cannot be empty")

        upper = cleaned.upper()

        # 1. Direct 3-letter IATA code check
        if IATA_RE.match(upper):
            if upper in cls._airports:
                return upper, cls._airports[upper]["name"]
            # Accept valid IATA format as passthrough even if unlisted
            return upper, f"Airport ({upper})"

        # 2. Check static nearest-airport override
        normalized = _strip_accents(cleaned).lower()
        if normalized in STATIC_NEAREST_AIRPORTS:
            return STATIC_NEAREST_AIRPORTS[normalized]

        # 3. Lookup in by_city index
        if normalized in cls._by_city:
            iata_list = cls._by_city[normalized]
            if iata_list:
                primary_iata = iata_list[0]
                airport_name = cls._airports.get(primary_iata, {}).get("name", f"Airport ({primary_iata})")
                return primary_iata, airport_name

        # 4. Substring / partial match across airports
        for iata, apt in cls._airports.items():
            apt_city = apt.get("normalized_city", "")
            apt_name = apt.get("name", "").lower()
            if normalized == apt_city or normalized in apt_name:
                return iata, apt.get("name", f"Airport ({iata})")

        raise AirportNotFoundError(
            f"Could not resolve '{query}' to an airport code. "
            "Please provide a recognized city name or 3-letter IATA code (e.g. 'Chennai' or 'MAA')."
        )

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
