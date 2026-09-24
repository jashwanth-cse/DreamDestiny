"""
State Capital Resolver
======================
Resolves railway stations to their designated State Capital station record
using data/state_capitals.json and the railway station dataset.

Example:
    Rajapalayam (RJPM)
    -> State: Tamil Nadu
    -> State Capital Station: Chennai Central (MAS)

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


def _find_state_capitals_path() -> Optional[Path]:
    """Locate state_capitals.json relative to common project layouts."""
    env = os.environ.get("STATE_CAPITALS_DATA_PATH")
    if env and Path(env).exists():
        return Path(env)

    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "state_capitals.json",
        Path("data/state_capitals.json"),
        Path("../data/state_capitals.json"),
        Path("../../data/state_capitals.json"),
        Path("/app/data/state_capitals.json"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    return None


class StateCapitalResolver:
    """
    In-memory resolver mapping Indian states and union territories to verified
    capital railway station records.
    """

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        station_resolver: Optional[RailwayStationResolver] = None,
    ) -> None:
        self._path: Optional[Path] = dataset_path
        self._station_resolver: Optional[RailwayStationResolver] = station_resolver
        self._capitals: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def load(self, dataset_path: Optional[Path] = None) -> None:
        """Load state_capitals.json into memory once."""
        if self._loaded:
            return

        target = dataset_path or self._path or _find_state_capitals_path()
        if target is None or not Path(target).exists():
            log.warning(
                "StateCapitalResolver: state_capitals.json not found. "
                "Run scripts/preprocess_state_capitals.py to generate it."
            )
            self._loaded = True
            return

        with open(target, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # Store with normalized uppercase keys for robust matching
        self._capitals = {k.strip().upper(): v for k, v in raw_data.items()}
        self._loaded = True
        log.info("StateCapitalResolver loaded %d state capitals from %s", len(self._capitals), Path(target).name)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get_capital_by_state(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Given a state/UT name (e.g. 'Tamil Nadu', 'Maharashtra', 'Delhi'),
        return the designated capital railway station record.
        """
        self._ensure_loaded()
        cleaned = (state or "").strip().upper()
        if not cleaned:
            return None

        # Direct match or handle slight typos/slash cases like 'MAHARASHTRA/GUJARA T'
        cap_meta = self._capitals.get(cleaned)
        if not cap_meta:
            for registered_state, meta in self._capitals.items():
                if registered_state in cleaned or cleaned in registered_state:
                    cap_meta = meta
                    break

        if not cap_meta:
            return None

        station_code = cap_meta.get("station_code")
        if not station_code:
            return None

        # Enrich from station resolver if available
        if self._station_resolver:
            stn = self._station_resolver.get_by_code(station_code)
            if stn:
                return {
                    "station_code": station_code,
                    "station_name": stn.get("station_name", cap_meta.get("station_name", station_code)),
                    "division": stn.get("division", ""),
                    "zone": stn.get("zone", ""),
                    "district": stn.get("district", ""),
                    "state": stn.get("state", state),
                    "latitude": 0.0,
                    "longitude": 0.0,
                }

        return {
            "station_code": station_code,
            "station_name": cap_meta.get("station_name", station_code),
            "division": "",
            "zone": "",
            "district": "",
            "state": state,
            "latitude": 0.0,
            "longitude": 0.0,
        }

    def get_capital(
        self,
        station_or_query: Union[Dict[str, Any], StationMatch, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve the state capital station for a given station record, StationMatch, or query string.
        """
        self._ensure_loaded()

        state: Optional[str] = None

        if isinstance(station_or_query, StationMatch):
            state = station_or_query.state
        elif isinstance(station_or_query, dict):
            state = station_or_query.get("state")
        elif isinstance(station_or_query, str):
            if self._station_resolver:
                match = self._station_resolver.resolve(station_or_query)
                state = match.state

        if not state:
            return None

        return self.get_capital_by_state(state)
