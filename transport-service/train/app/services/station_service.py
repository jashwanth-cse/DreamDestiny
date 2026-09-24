"""
Station Search Service
======================
Resolves city names, station names, and IRCTC station codes to station records
used for train searches.

Resolution priority (fast → slow):
  1. Direct station code passthrough (2–5 letter uppercase, e.g. "MAS")     [< 0.01 ms]
  2. Pre-seeded instant table (100+ major cities/junctions)                  [< 0.01 ms]
  3. LOCAL railway_stations.json resolver (8,600+ IRCTC stations)            [< 1 ms   ]
     3a. Exact normalized name match
     3b. Alias match (station_aliases.json)
     3c. High-confidence deterministic fuzzy match (Jaccard ≥ 0.82)
  4. External Ixigo Station API (network, cached in LRU)                     [~400 ms  ]
     - Used when the local resolver returns NOT_FOUND or AMBIGUOUS.

Design rules:
  - Steps 1–3 are zero-network and sub-millisecond.
  - Step 4 fires only when all local steps fail.
  - The external API remains unchanged; nothing removes it.
  - Metrics (local_hit / local_miss / ambiguous / api_fallback) are logged at INFO.
  - Thread-safe: the local resolver index is read-only after startup load.

Lookup metrics emitted at INFO level per request:
  [station_resolver] local_hit   (exact)   'sivakasi'  → SVKS  (0.042 ms)
  [station_resolver] local_hit   (code)    'MAS'       → MAS   (0.003 ms)
  [station_resolver] local_miss            'unknownx'           (0.021 ms) → api_fallback
  [station_resolver] ambiguous             'karur'              (0.053 ms) → api_fallback
  [station_resolver] fuzzy_hit             'sengottai' → SCT   (0.310 ms)
"""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests

from app.config import config
from app.exceptions import StationNotFoundError
from app.resolver.railway_station_resolver import RailwayStationResolver, ResolveStatus
from app.utils import parse_station

logger = logging.getLogger(__name__)

# ── Global session for connection pooling ─────────────────────────────────────
_session = requests.Session()

# ── Module-level resolver singleton (loaded once at import time) ──────────────
_resolver = RailwayStationResolver()

def _ensure_resolver_loaded() -> None:
    """Ensure the resolver dataset is loaded. Called lazily on first use."""
    if not _resolver._loaded:
        _resolver.load()

# ── Pre-seeded Top Indian Stations & Hubs (instant 0-latency fast-path) ───────
# Kept verbatim from the original station_service.py.  This table wins over the
# JSON dataset for the listed cities, preserving backward-compatible behavior.
PRESEEDED_STATIONS: Dict[str, Dict[str, Any]] = {
    # ── Metro & Major Hubs ───────────────────────────────────────────────────
    "chennai": {"station_name": "Chennai - All stations", "station_code": "MAS", "latitude": 13.0827, "longitude": 80.2707},
    "chennai central": {"station_name": "MGR Chennai Central", "station_code": "MAS", "latitude": 13.0827, "longitude": 80.2707},
    "chennai egmore": {"station_name": "Chennai Egmore", "station_code": "MS", "latitude": 13.0792, "longitude": 80.2610},
    "madras": {"station_name": "Chennai - All stations", "station_code": "MAS", "latitude": 13.0827, "longitude": 80.2707},

    "delhi": {"station_name": "Delhi - All stations", "station_code": "NDLS", "latitude": 28.6139, "longitude": 77.2090},
    "new delhi": {"station_name": "New Delhi", "station_code": "NDLS", "latitude": 28.6415, "longitude": 77.2185},
    "old delhi": {"station_name": "Delhi", "station_code": "DLI", "latitude": 28.6606, "longitude": 77.2289},
    "hazrat nizamuddin": {"station_name": "Hazrat Nizamuddin", "station_code": "NZM", "latitude": 28.5888, "longitude": 77.2534},

    "mumbai": {"station_name": "Mumbai - All stations", "station_code": "CSMT", "latitude": 18.9402, "longitude": 72.8354},
    "mumbai csmt": {"station_name": "Chhatrapati Shivaji Maharaj Terminus", "station_code": "CSMT", "latitude": 18.9402, "longitude": 72.8354},
    "mumbai central": {"station_name": "Mumbai Central", "station_code": "MMCT", "latitude": 18.9696, "longitude": 72.8193},
    "lokmanya tilak": {"station_name": "Lokmanya Tilak Terminus", "station_code": "LTT", "latitude": 19.0691, "longitude": 72.8914},
    "bandra": {"station_name": "Bandra Terminus", "station_code": "BDTS", "latitude": 19.0607, "longitude": 72.8407},
    "bombay": {"station_name": "Mumbai - All stations", "station_code": "CSMT", "latitude": 18.9402, "longitude": 72.8354},

    "bangalore": {"station_name": "Bengaluru - All stations", "station_code": "SBC", "latitude": 12.9774, "longitude": 77.5729},
    "bengaluru": {"station_name": "Bengaluru - All stations", "station_code": "SBC", "latitude": 12.9774, "longitude": 77.5729},
    "ksr bengaluru": {"station_name": "KSR Bengaluru", "station_code": "SBC", "latitude": 12.9774, "longitude": 77.5729},
    "yesvantpur": {"station_name": "Yesvantpur Jn", "station_code": "YPR", "latitude": 13.0238, "longitude": 77.5501},

    "kolkata": {"station_name": "Howrah Jn", "station_code": "HWH", "latitude": 22.5838, "longitude": 88.3426},
    "howrah": {"station_name": "Howrah Jn", "station_code": "HWH", "latitude": 22.5838, "longitude": 88.3426},
    "sealdah": {"station_name": "Sealdah", "station_code": "SDAH", "latitude": 22.5697, "longitude": 88.3711},
    "calcutta": {"station_name": "Howrah Jn", "station_code": "HWH", "latitude": 22.5838, "longitude": 88.3426},

    "hyderabad": {"station_name": "Secunderabad Jn", "station_code": "SC", "latitude": 17.4344, "longitude": 78.5017},
    "secunderabad": {"station_name": "Secunderabad Jn", "station_code": "SC", "latitude": 17.4344, "longitude": 78.5017},
    "kacheguda": {"station_name": "Kacheguda", "station_code": "KCG", "latitude": 17.3899, "longitude": 78.4975},

    # ── Tamil Nadu & South India ──────────────────────────────────────────────
    "coimbatore": {"station_name": "Coimbatore Jn", "station_code": "CBE", "latitude": 11.0018, "longitude": 76.9629},
    "madurai": {"station_name": "Madurai Jn", "station_code": "MDU", "latitude": 9.9196, "longitude": 78.1100},
    "rajapalayam": {"station_name": "Rajapalayam", "station_code": "RJPM", "latitude": 9.4522, "longitude": 77.5612},
    "sivakasi": {"station_name": "Sivakasi", "station_code": "SVKS", "latitude": 9.4629, "longitude": 77.7880},
    "srivilliputtur": {"station_name": "Srivilliputtur", "station_code": "SVPR", "latitude": 9.4973, "longitude": 77.6445},
    "virudhunagar": {"station_name": "Virudunagar Jn", "station_code": "VPT", "latitude": 9.5946, "longitude": 77.9579},
    "virudunagar": {"station_name": "Virudunagar Jn", "station_code": "VPT", "latitude": 9.5946, "longitude": 77.9579},
    "tenkasi": {"station_name": "Tenkasi Jn", "station_code": "TSI", "latitude": 8.9592, "longitude": 77.3150},
    "sengottai": {"station_name": "Sengottai", "station_code": "SCT", "latitude": 8.9833, "longitude": 77.2667},
    "tirunelveli": {"station_name": "Tirunelveli Jn", "station_code": "TEN", "latitude": 8.7274, "longitude": 77.7126},
    "tuticorin": {"station_name": "Tuticorin", "station_code": "TN", "latitude": 8.7642, "longitude": 78.1348},
    "thoothukudi": {"station_name": "Tuticorin", "station_code": "TN", "latitude": 8.7642, "longitude": 78.1348},
    "kanyakumari": {"station_name": "Kanyakumari", "station_code": "CAPE", "latitude": 8.0883, "longitude": 77.5385},
    "nagercoil": {"station_name": "Nagercoil Jn", "station_code": "NCJ", "latitude": 8.1833, "longitude": 77.4119},
    "dindigul": {"station_name": "Dindigul Jn", "station_code": "DG", "latitude": 10.3673, "longitude": 77.9803},
    "trichy": {"station_name": "Tiruchchirappalli Jn", "station_code": "TPJ", "latitude": 10.7946, "longitude": 78.6856},
    "tiruchchirappalli": {"station_name": "Tiruchchirappalli Jn", "station_code": "TPJ", "latitude": 10.7946, "longitude": 78.6856},
    "thanjavur": {"station_name": "Thanjavur Jn", "station_code": "TJ", "latitude": 10.7870, "longitude": 79.1378},
    "tanjore": {"station_name": "Thanjavur Jn", "station_code": "TJ", "latitude": 10.7870, "longitude": 79.1378},
    "kumbakonam": {"station_name": "Kumbakonam", "station_code": "KMU", "latitude": 10.9602, "longitude": 79.3845},
    "salem": {"station_name": "Salem Jn", "station_code": "SA", "latitude": 11.6643, "longitude": 78.1460},
    "erode": {"station_name": "Erode Jn", "station_code": "ED", "latitude": 11.3410, "longitude": 77.7172},
    "tiruppur": {"station_name": "Tiruppur", "station_code": "TUP", "latitude": 11.1085, "longitude": 77.3411},
    "vellore": {"station_name": "Katpadi Jn", "station_code": "KPD", "latitude": 12.9698, "longitude": 79.1368},
    "katpadi": {"station_name": "Katpadi Jn", "station_code": "KPD", "latitude": 12.9698, "longitude": 79.1368},
    "hosur": {"station_name": "Hosur", "station_code": "HSRA", "latitude": 12.7409, "longitude": 77.8253},
    "pondicherry": {"station_name": "Puducherry", "station_code": "PDY", "latitude": 11.9338, "longitude": 79.8297},
    "puducherry": {"station_name": "Puducherry", "station_code": "PDY", "latitude": 11.9338, "longitude": 79.8297},

    # ── Kerala & Karnataka ───────────────────────────────────────────────────
    "kochi": {"station_name": "Ernakulam Jn", "station_code": "ERS", "latitude": 9.9678, "longitude": 76.2917},
    "cochin": {"station_name": "Ernakulam Jn", "station_code": "ERS", "latitude": 9.9678, "longitude": 76.2917},
    "ernakulam": {"station_name": "Ernakulam Jn", "station_code": "ERS", "latitude": 9.9678, "longitude": 76.2917},
    "trivandrum": {"station_name": "Thiruvananthapuram Central", "station_code": "TVC", "latitude": 8.4875, "longitude": 76.9525},
    "thiruvananthapuram": {"station_name": "Thiruvananthapuram Central", "station_code": "TVC", "latitude": 8.4875, "longitude": 76.9525},
    "calicut": {"station_name": "Kozhikode Main", "station_code": "CLT", "latitude": 11.2480, "longitude": 75.7839},
    "kozhikode": {"station_name": "Kozhikode Main", "station_code": "CLT", "latitude": 11.2480, "longitude": 75.7839},
    "thrissur": {"station_name": "Thrissur", "station_code": "TCR", "latitude": 10.5160, "longitude": 76.2133},
    "palakkad": {"station_name": "Palakkad Jn", "station_code": "PGT", "latitude": 10.7867, "longitude": 76.6548},
    "kollam": {"station_name": "Kollam Jn", "station_code": "QLN", "latitude": 8.8879, "longitude": 76.5956},
    "alleppey": {"station_name": "Alappuzha", "station_code": "ALLP", "latitude": 9.4920, "longitude": 76.3264},
    "alappuzha": {"station_name": "Alappuzha", "station_code": "ALLP", "latitude": 9.4920, "longitude": 76.3264},
    "mysore": {"station_name": "Mysuru Jn", "station_code": "MYS", "latitude": 12.3160, "longitude": 76.6450},
    "mysuru": {"station_name": "Mysuru Jn", "station_code": "MYS", "latitude": 12.3160, "longitude": 76.6450},
    "mangalore": {"station_name": "Mangaluru Central", "station_code": "MAQ", "latitude": 12.8654, "longitude": 74.8426},
    "mangaluru": {"station_name": "Mangaluru Central", "station_code": "MAQ", "latitude": 12.8654, "longitude": 74.8426},
    "hubli": {"station_name": "SSS Hubballi Jn", "station_code": "UBL", "latitude": 15.3486, "longitude": 75.1472},
    "hubballi": {"station_name": "SSS Hubballi Jn", "station_code": "UBL", "latitude": 15.3486, "longitude": 75.1472},

    # ── Andhra & Telangana ───────────────────────────────────────────────────
    "vijayawada": {"station_name": "Vijayawada Jn", "station_code": "BZA", "latitude": 16.5186, "longitude": 80.6200},
    "visakhapatnam": {"station_name": "Visakhapatnam", "station_code": "VSKP", "latitude": 17.7206, "longitude": 83.2847},
    "vizag": {"station_name": "Visakhapatnam", "station_code": "VSKP", "latitude": 17.7206, "longitude": 83.2847},
    "tirupati": {"station_name": "Tirupati", "station_code": "TPTY", "latitude": 13.6288, "longitude": 79.4192},
    "warangal": {"station_name": "Kazipet Jn", "station_code": "KZJ", "latitude": 17.9808, "longitude": 79.5222},
    "guntur": {"station_name": "Guntur Jn", "station_code": "GNT", "latitude": 16.2990, "longitude": 80.4430},

    # ── West & Central India ─────────────────────────────────────────────────
    "pune": {"station_name": "Pune Jn", "station_code": "PUNE", "latitude": 18.5284, "longitude": 73.8743},
    "ahmedabad": {"station_name": "Ahmedabad Jn", "station_code": "ADI", "latitude": 23.0225, "longitude": 72.5714},
    "surat": {"station_name": "Surat", "station_code": "ST", "latitude": 21.2052, "longitude": 72.8407},
    "vadodara": {"station_name": "Vadodara Jn", "station_code": "BRC", "latitude": 22.3107, "longitude": 73.1812},
    "baroda": {"station_name": "Vadodara Jn", "station_code": "BRC", "latitude": 22.3107, "longitude": 73.1812},
    "bhopal": {"station_name": "Bhopal Jn", "station_code": "BPL", "latitude": 23.2599, "longitude": 77.4126},
    "nagpur": {"station_name": "Nagpur Jn", "station_code": "NGP", "latitude": 21.1528, "longitude": 79.0882},
    "indore": {"station_name": "Indore Jn", "station_code": "INDB", "latitude": 22.7196, "longitude": 75.8577},
    "gwalior": {"station_name": "Gwalior Jn", "station_code": "GWL", "latitude": 26.2183, "longitude": 78.1828},
    "jabalpur": {"station_name": "Jabalpur Jn", "station_code": "JBP", "latitude": 23.1686, "longitude": 79.9339},
    "goa": {"station_name": "Madgaon Jn", "station_code": "MAO", "latitude": 15.2755, "longitude": 73.9788},
    "madgaon": {"station_name": "Madgaon Jn", "station_code": "MAO", "latitude": 15.2755, "longitude": 73.9788},

    # ── North & East India ───────────────────────────────────────────────────
    "jaipur": {"station_name": "Jaipur Jn", "station_code": "JP", "latitude": 26.9200, "longitude": 75.7878},
    "jodhpur": {"station_name": "Jodhpur Jn", "station_code": "JU", "latitude": 26.2800, "longitude": 73.0200},
    "udaipur": {"station_name": "Udaipur City", "station_code": "UDZ", "latitude": 24.5854, "longitude": 73.7125},
    "agra": {"station_name": "Agra Cantt", "station_code": "AGC", "latitude": 27.1587, "longitude": 78.0081},
    "lucknow": {"station_name": "Lucknow Charbagh", "station_code": "LKO", "latitude": 26.8322, "longitude": 80.9238},
    "varanasi": {"station_name": "Varanasi Jn", "station_code": "BSB", "latitude": 25.3283, "longitude": 82.9868},
    "kanpur": {"station_name": "Kanpur Central", "station_code": "CNB", "latitude": 26.4547, "longitude": 80.3507},
    "prayagraj": {"station_name": "Prayagraj Jn", "station_code": "PRYJ", "latitude": 25.4484, "longitude": 81.8344},
    "allahabad": {"station_name": "Prayagraj Jn", "station_code": "PRYJ", "latitude": 25.4484, "longitude": 81.8344},
    "patna": {"station_name": "Patna Jn", "station_code": "PNBE", "latitude": 25.6022, "longitude": 85.1376},
    "bhubaneswar": {"station_name": "Bhubaneswar", "station_code": "BBS", "latitude": 20.2644, "longitude": 85.8443},
    "puri": {"station_name": "Puri", "station_code": "PURI", "latitude": 19.8135, "longitude": 85.8312},
    "ranchi": {"station_name": "Ranchi Jn", "station_code": "RNC", "latitude": 23.3500, "longitude": 85.3300},
    "raipur": {"station_name": "Raipur Jn", "station_code": "R", "latitude": 21.2514, "longitude": 81.6296},
    "guwahati": {"station_name": "Guwahati", "station_code": "GHY", "latitude": 26.1837, "longitude": 91.7511},
    "amritsar": {"station_name": "Amritsar Jn", "station_code": "ASR", "latitude": 31.6340, "longitude": 74.8723},
    "chandigarh": {"station_name": "Chandigarh", "station_code": "CDG", "latitude": 30.7046, "longitude": 76.7179},
    "dehradun": {"station_name": "Dehradun", "station_code": "DDN", "latitude": 30.3165, "longitude": 78.0322},
    "haridwar": {"station_name": "Haridwar", "station_code": "HW", "latitude": 29.9457, "longitude": 78.1642},
    "katra": {"station_name": "SMVD Katra", "station_code": "SVDK", "latitude": 32.9912, "longitude": 74.9315},
    "jammu": {"station_name": "Jammu Tawi", "station_code": "JAT", "latitude": 32.7060, "longitude": 74.8800},
}

# Valid station code pattern
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,6}$")


# ── External API cache (unchanged from original) ──────────────────────────────

@lru_cache(maxsize=4096)
def _fetch_from_api_cached(station_name_key: str) -> List[Dict[str, Any]]:
    """
    Internal cached fetcher for stations from the Ixigo API.
    Cached indefinitely in memory across all requests.
    """
    params = {
        "searchFor": "trainstationsLatLon",
        "anchor": "false",
        "value": station_name_key,
    }

    try:
        response = _session.get(
            config.STATION_API,
            params=params,
            headers=config.STATION_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.warning("Station API request failed for '%s': %s", station_name_key, e)
        return []

    stations: List[Dict[str, Any]] = []
    for item in data:
        station = parse_station(item.get("e", ""))
        if station is None:
            continue
        try:
            station["latitude"]  = float(item.get("lat", 0.0))
            station["longitude"] = float(item.get("lon", 0.0))
        except (ValueError, TypeError):
            station["latitude"]  = 0.0
            station["longitude"] = 0.0
        stations.append(station)

    return tuple(stations)   # type: ignore[return-value]  lru_cache needs hashable


# ── StationService ────────────────────────────────────────────────────────────

class StationService:
    """
    Ultra-low latency station resolution service.

    Priority:
      1. Pre-seeded instant table       (< 0.01 ms)
      2. Direct station code match      (< 0.01 ms)
      3. Local JSON resolver            (< 1 ms, zero-network)
      4. External Ixigo API + LRU cache (~400 ms first call, cached thereafter)
    """

    def __init__(self) -> None:
        self.url     = config.STATION_API
        self.headers = config.STATION_HEADERS
        _ensure_resolver_loaded()   # warm the local resolver at construction time

    def search(self, station_name: str) -> List[Dict[str, Any]]:
        """Search for stations matching a name (returns a list for compatibility)."""
        cleaned = station_name.strip().lower()
        if not cleaned:
            return []

        # 1. Pre-seeded instant table
        if cleaned in PRESEEDED_STATIONS:
            return [PRESEEDED_STATIONS[cleaned]]

        # 2. Local resolver
        match = _resolver.resolve(station_name)
        if not match.needs_api_fallback:
            rec = match.to_station_dict()
            return [rec] if rec else []

        # 3. External API
        return list(_fetch_from_api_cached(cleaned))

    def get_station_code(self, station_name: str) -> str:
        """Return primary station code for a given name."""
        return self.get_station(station_name)["station_code"]

    def get_station(self, station_name: str) -> Dict[str, Any]:
        """
        Returns full station dict: {station_name, station_code, latitude, longitude, ...}.

        Resolution priority:
          1. Pre-seeded instant table
          2. Direct station code passthrough
          3. Local JSON resolver (exact → alias → fuzzy)
          4. External Ixigo API (network, cached)

        Raises StationNotFoundError if all steps fail.
        """
        cleaned = station_name.strip()
        if not cleaned:
            raise StationNotFoundError("Empty station name provided")

        lower = cleaned.lower()

        # ── Step 1: Pre-seeded table (covers all major cities) ───────────────
        if lower in PRESEEDED_STATIONS:
            logger.info(
                "[station_resolver] local_hit (preseeded) '%s' → %s",
                station_name, PRESEEDED_STATIONS[lower]["station_code"]
            )
            return PRESEEDED_STATIONS[lower]

        # ── Step 2: Direct station code passthrough ──────────────────────────
        upper = cleaned.upper()
        if _CODE_RE.match(upper):
            # Check preseeded values first
            for s in PRESEEDED_STATIONS.values():
                if s["station_code"] == upper:
                    logger.info(
                        "[station_resolver] local_hit (code→preseeded) '%s' → %s",
                        station_name, upper
                    )
                    return s
            # Try local resolver
            match = _resolver.resolve(upper)
            if not match.needs_api_fallback:
                rec = match.to_station_dict()
                if rec:
                    logger.info(
                        "[station_resolver] local_hit (code) '%s' → %s [%.3f ms]",
                        station_name, upper, match.latency_ms
                    )
                    return rec

        # ── Step 3: Local JSON resolver ──────────────────────────────────────
        match = _resolver.resolve(cleaned)

        if match.status.value == "exact" or match.status.value == "fuzzy":
            rec = match.to_station_dict()
            if rec:
                logger.info(
                    "[station_resolver] local_hit (%s) '%s' → %s [%.3f ms]",
                    match.status.value, station_name, match.station_code, match.latency_ms
                )
                return rec

        if match.status.value == "ambiguous":
            logger.info(
                "[station_resolver] ambiguous '%s' → candidates %s [%.3f ms] → api_fallback",
                station_name, match.candidates[:5], match.latency_ms
            )
            # Fall through to API which may disambiguate via user's exact query string

        if match.status.value == "not_found":
            logger.info(
                "[station_resolver] local_miss '%s' [%.3f ms] → api_fallback",
                station_name, match.latency_ms
            )

        # ── Step 4: External Ixigo API ───────────────────────────────────────
        logger.info("[station_resolver] api_fallback for '%s'", station_name)
        stations = list(_fetch_from_api_cached(lower))
        if not stations:
            raise StationNotFoundError(
                f"No station found for '{station_name}'. "
                "Please provide a valid city name or IRCTC station code (e.g. 'Sivakasi' or 'SVKS')."
            )
        return stations[0]