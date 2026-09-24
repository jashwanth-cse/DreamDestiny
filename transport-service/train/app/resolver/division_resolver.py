"""
Division Resolver
=================
Resolves railway stations to their designated Division Hub station record
using data/division_hubs.json and the railway station dataset.

Example:
    Rajapalayam (RJPM)
    -> Division: MDU
    -> Division Hub: Madurai Jn (MDU)

Loaded once at startup. Thread-safe and in-memory.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.resolver.railway_station_resolver import RailwayStationResolver, StationMatch

log = logging.getLogger(__name__)


def _find_division_hubs_path() -> Optional[Path]:
    """Locate division_hubs.json relative to common project layouts."""
    env = os.environ.get("DIVISION_HUBS_DATA_PATH")
    if env and Path(env).exists():
        return Path(env)

    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "division_hubs.json",
        Path("data/division_hubs.json"),
        Path("../data/division_hubs.json"),
        Path("../../data/division_hubs.json"),
        Path("/app/data/division_hubs.json"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    return None


class DivisionResolver:
    """
    In-memory resolver mapping railway divisions to verified hub station records.
    """

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        station_resolver: Optional[RailwayStationResolver] = None,
    ) -> None:
        self._path: Optional[Path] = dataset_path
        self._station_resolver: Optional[RailwayStationResolver] = station_resolver
        self._hubs: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def load(self, dataset_path: Optional[Path] = None) -> None:
        """Load division_hubs.json into memory once."""
        if self._loaded:
            return

        target = dataset_path or self._path or _find_division_hubs_path()
        if target is None or not Path(target).exists():
            log.warning(
                "DivisionResolver: division_hubs.json not found. "
                "Run scripts/preprocess_division_hubs.py to generate it."
            )
            self._loaded = True
            return

        with open(target, "r", encoding="utf-8") as f:
            self._hubs = json.load(f)

        self._loaded = True
        log.info("DivisionResolver loaded %d division hubs from %s", len(self._hubs), Path(target).name)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get_hub_by_division(self, division: str) -> Optional[Dict[str, Any]]:
        """
        Given a railway division code (e.g. 'MDU', 'MAS', 'DLI', 'BSL'),
        return the designated hub station record.
        """
        self._ensure_loaded()
        cleaned = (division or "").strip().upper()
        if not cleaned or cleaned not in self._hubs:
            return None

        hub_meta = self._hubs[cleaned]
        hub_code = hub_meta.get("hub_code")
        if not hub_code:
            return None

        # Enrich from station resolver if available
        if self._station_resolver:
            stn = self._station_resolver.get_by_code(hub_code)
            if stn:
                return {
                    "station_code": hub_code,
                    "station_name": stn.get("station_name", hub_meta.get("hub_name", hub_code)),
                    "division": stn.get("division", cleaned),
                    "zone": stn.get("zone", hub_meta.get("zone", "")),
                    "district": stn.get("district", ""),
                    "state": stn.get("state", ""),
                    "latitude": 0.0,
                    "longitude": 0.0,
                }

        return {
            "station_code": hub_code,
            "station_name": hub_meta.get("hub_name", hub_code),
            "division": cleaned,
            "zone": hub_meta.get("zone", ""),
            "district": "",
            "state": "",
            "latitude": 0.0,
            "longitude": 0.0,
        }

    def get_hub(
        self,
        station_or_query: Union[Dict[str, Any], StationMatch, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve the division hub for a given station record, StationMatch, or query string.
        """
        self._ensure_loaded()

        division: Optional[str] = None

        if isinstance(station_or_query, StationMatch):
            division = station_or_query.division
        elif isinstance(station_or_query, dict):
            division = station_or_query.get("division")
        elif isinstance(station_or_query, str):
            if self._station_resolver:
                match = self._station_resolver.resolve(station_or_query)
                division = match.division

        if not division:
            return None

        return self.get_hub_by_division(division)
