"""
Route Fallback Service
======================
Implements verified 3-level train route fallback hierarchy:

    LEVEL 1 — Direct route: source -> destination
    LEVEL 2 — Division fallback: source_division_hub -> dest_division_hub
    LEVEL 3 — State-capital fallback: source_state_capital -> dest_state_capital

Rules:
  - Local station resolution requires zero external network calls.
  - Fallback is ONLY triggered when the train source explicitly returns NO DIRECT TRAINS.
  - An API error, timeout, or HTTP error must NEVER trigger fallback (it must raise).
  - Routes are deduplicated before querying to prevent redundant API calls.
  - Returns structured metadata detailing route_type, original_source, actual_source,
    fallback_reason, and fallback_searches_count.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.resolver.division_resolver import DivisionResolver
from app.resolver.railway_station_resolver import RailwayStationResolver
from app.resolver.state_capital_resolver import StateCapitalResolver
from app.services.station_service import StationService

logger = logging.getLogger(__name__)


def _clean_station_info(station_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Produce a clean, consistent station metadata dict for API responses."""
    if not station_dict:
        return None
    return {
        "station_code": station_dict.get("station_code", ""),
        "station_name": station_dict.get("station_name", ""),
        "division": station_dict.get("division") or "",
        "zone": station_dict.get("zone") or "",
        "state": station_dict.get("state") or "",
        "district": station_dict.get("district") or "",
    }


class RouteFallbackService:
    """
    Coordinates multi-level route resolution and verified fallback train searches.
    """

    def __init__(
        self,
        station_service: Optional[StationService] = None,
        division_resolver: Optional[DivisionResolver] = None,
        state_capital_resolver: Optional[StateCapitalResolver] = None,
        train_service: Optional[Any] = None,
    ) -> None:
        self.station_service = station_service or StationService()

        # Shared underlying station resolver instance if available
        base_stn_resolver = getattr(self.station_service, "_resolver", None)
        if not base_stn_resolver:
            base_stn_resolver = RailwayStationResolver()
            base_stn_resolver.load()

        self.station_resolver = base_stn_resolver
        self.division_resolver = division_resolver or DivisionResolver(station_resolver=base_stn_resolver)
        self.state_capital_resolver = state_capital_resolver or StateCapitalResolver(station_resolver=base_stn_resolver)

        # Lazy import of train_service to prevent circular import if passed None
        if train_service is not None:
            self.train_service = train_service
        else:
            from app.services.train_service import TrainService
            self.train_service = TrainService(station_service=self.station_service)

    def search_with_fallback(
        self,
        source: str,
        destination: str,
        journey_date: str,
        travel_class: Optional[str] = None,
        sort_by: str = "departure",
        max_fare: Optional[int] = None,
        min_rating: Optional[float] = None,
        pantry: Optional[bool] = None,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """
        Executes verified route search following the 3-level fallback hierarchy.
        """
        t0 = time.perf_counter()

        # ── Step 0: Resolve stations locally (< 0.2 ms, zero network) ────────
        orig_source_station = dict(self.station_service.get_station(source))
        orig_dest_station = dict(self.station_service.get_station(destination))

        # Enrich division/state from dataset if missing (e.g. from preseeded table)
        if not orig_source_station.get("division"):
            meta = self.station_resolver.get_by_code(orig_source_station["station_code"])
            if meta:
                for k in ("division", "zone", "state", "district"):
                    if not orig_source_station.get(k):
                        orig_source_station[k] = meta.get(k) or ""

        if not orig_dest_station.get("division"):
            meta = self.station_resolver.get_by_code(orig_dest_station["station_code"])
            if meta:
                for k in ("division", "zone", "state", "district"):
                    if not orig_dest_station.get(k):
                        orig_dest_station[k] = meta.get(k) or ""

        orig_src_code = orig_source_station["station_code"]
        orig_dst_code = orig_dest_station["station_code"]

        searches_attempted = 0

        # ── LEVEL 1: Direct Route ────────────────────────────────────────────
        logger.info(
            "[route_fallback] Level 1: searching direct route %s (%s) -> %s (%s)",
            orig_source_station["station_name"], orig_src_code,
            orig_dest_station["station_name"], orig_dst_code
        )

        # Direct search: raises on network/HTTP error (does NOT trigger fallback)
        direct_result = self.train_service.search_direct(
            source_station=orig_source_station,
            dest_station=orig_dest_station,
            journey_date=journey_date,
            travel_class=travel_class,
            sort_by=sort_by,
            max_fare=max_fare,
            min_rating=min_rating,
            pantry=pantry,
            quota=quota,
        )
        searches_attempted += 1

        direct_trains = direct_result.get("trains", [])
        if direct_trains:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            direct_result.update({
                "route_type": "direct",
                "original_source": _clean_station_info(orig_source_station),
                "original_destination": _clean_station_info(orig_dest_station),
                "actual_source": _clean_station_info(orig_source_station),
                "actual_destination": _clean_station_info(orig_dest_station),
                "fallback_reason": None,
                "fallback_searches_count": searches_attempted,
                "latency_ms": round(elapsed_ms, 2),
            })
            logger.info(
                "[route_fallback] direct route found %d train(s) (searches: %d, time: %.1fms)",
                len(direct_trains), searches_attempted, elapsed_ms
            )
            return direct_result

        # ── LEVEL 2: Division Fallback ───────────────────────────────────────
        logger.info(
            "[route_fallback] Level 1 returned 0 direct trains. Evaluating Level 2 (Division Fallback)..."
        )

        src_hub = self.division_resolver.get_hub(orig_source_station)
        dst_hub = self.division_resolver.get_hub(orig_dest_station)

        # Fallback to original station if division hub is not found or is the same
        effective_src_hub = src_hub or orig_source_station
        effective_dst_hub = dst_hub or orig_dest_station

        hub_src_code = effective_src_hub["station_code"]
        hub_dst_code = effective_dst_hub["station_code"]

        # Check deduplication against Level 1 and self-loops
        is_same_as_direct = (hub_src_code == orig_src_code and hub_dst_code == orig_dst_code)
        is_self_loop = (hub_src_code == hub_dst_code)

        if not is_same_as_direct and not is_self_loop:
            logger.info(
                "[route_fallback] Level 2: searching division hub route %s (%s) -> %s (%s)",
                effective_src_hub["station_name"], hub_src_code,
                effective_dst_hub["station_name"], hub_dst_code
            )

            div_result = self.train_service.search_direct(
                source_station=effective_src_hub,
                dest_station=effective_dst_hub,
                journey_date=journey_date,
                travel_class=travel_class,
                sort_by=sort_by,
                max_fare=max_fare,
                min_rating=min_rating,
                pantry=pantry,
                quota=quota,
            )
            searches_attempted += 1

            div_trains = div_result.get("trains", [])
            if div_trains:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                div_result.update({
                    "route_type": "division_fallback",
                    "original_source": _clean_station_info(orig_source_station),
                    "original_destination": _clean_station_info(orig_dest_station),
                    "actual_source": _clean_station_info(effective_src_hub),
                    "actual_destination": _clean_station_info(effective_dst_hub),
                    "fallback_reason": (
                        f"No direct trains found between {orig_source_station['station_name']} ({orig_src_code}) "
                        f"and {orig_dest_station['station_name']} ({orig_dst_code}). "
                        f"Found verified trains via division hubs {effective_src_hub['station_name']} ({hub_src_code}) "
                        f"and {effective_dst_hub['station_name']} ({hub_dst_code})."
                    ),
                    "fallback_searches_count": searches_attempted,
                    "latency_ms": round(elapsed_ms, 2),
                })
                logger.info(
                    "[route_fallback] division fallback found %d train(s) (searches: %d, time: %.1fms)",
                    len(div_trains), searches_attempted, elapsed_ms
                )
                return div_result
        else:
            logger.info(
                "[route_fallback] Level 2 skipped: division hubs (%s -> %s) duplicate direct route or self-loop",
                hub_src_code, hub_dst_code
            )

        # ── LEVEL 3: State-Capital Fallback ──────────────────────────────────
        logger.info(
            "[route_fallback] Level 2 yielded 0 trains. Evaluating Level 3 (State-Capital Fallback)..."
        )

        src_capital = self.state_capital_resolver.get_capital(orig_source_station)
        dst_capital = self.state_capital_resolver.get_capital(orig_dest_station)

        effective_src_cap = src_capital or orig_source_station
        effective_dst_cap = dst_capital or orig_dest_station

        cap_src_code = effective_src_cap["station_code"]
        cap_dst_code = effective_dst_cap["station_code"]

        # Check deduplication against Level 1, Level 2, and self-loops
        is_same_as_direct_3 = (cap_src_code == orig_src_code and cap_dst_code == orig_dst_code)
        is_same_as_div_3 = (cap_src_code == hub_src_code and cap_dst_code == hub_dst_code)
        is_self_loop_3 = (cap_src_code == cap_dst_code)

        if not is_same_as_direct_3 and not is_same_as_div_3 and not is_self_loop_3:
            logger.info(
                "[route_fallback] Level 3: searching state capital route %s (%s) -> %s (%s)",
                effective_src_cap["station_name"], cap_src_code,
                effective_dst_cap["station_name"], cap_dst_code
            )

            cap_result = self.train_service.search_direct(
                source_station=effective_src_cap,
                dest_station=effective_dst_cap,
                journey_date=journey_date,
                travel_class=travel_class,
                sort_by=sort_by,
                max_fare=max_fare,
                min_rating=min_rating,
                pantry=pantry,
                quota=quota,
            )
            searches_attempted += 1

            cap_trains = cap_result.get("trains", [])
            if cap_trains:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                cap_result.update({
                    "route_type": "state_capital_fallback",
                    "original_source": _clean_station_info(orig_source_station),
                    "original_destination": _clean_station_info(orig_dest_station),
                    "actual_source": _clean_station_info(effective_src_cap),
                    "actual_destination": _clean_station_info(effective_dst_cap),
                    "fallback_reason": (
                        f"No direct trains found between {orig_source_station['station_name']} ({orig_src_code}) "
                        f"and {orig_dest_station['station_name']} ({orig_dst_code}), or their division hubs. "
                        f"Found verified trains via state capitals {effective_src_cap['station_name']} ({cap_src_code}) "
                        f"and {effective_dst_cap['station_name']} ({cap_dst_code})."
                    ),
                    "fallback_searches_count": searches_attempted,
                    "latency_ms": round(elapsed_ms, 2),
                })
                logger.info(
                    "[route_fallback] state capital fallback found %d train(s) (searches: %d, time: %.1fms)",
                    len(cap_trains), searches_attempted, elapsed_ms
                )
                return cap_result
        else:
            logger.info(
                "[route_fallback] Level 3 skipped: state capitals (%s -> %s) duplicate previous searches or self-loop",
                cap_src_code, cap_dst_code
            )

        # ── LEVEL 4: No Route Found ──────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[route_fallback] no route found for %s -> %s after %d search(es) (time: %.1fms)",
            orig_src_code, orig_dst_code, searches_attempted, elapsed_ms
        )

        return {
            "result_type": "none",
            "source": orig_source_station["station_name"],
            "destination": orig_dest_station["station_name"],
            "total_trains": 0,
            "trains": [],
            "route_type": "no_route_found",
            "original_source": _clean_station_info(orig_source_station),
            "original_destination": _clean_station_info(orig_dest_station),
            "actual_source": _clean_station_info(orig_source_station),
            "actual_destination": _clean_station_info(orig_dest_station),
            "fallback_reason": (
                f"No direct trains found between {orig_source_station['station_name']} ({orig_src_code}) "
                f"and {orig_dest_station['station_name']} ({orig_dst_code}), "
                "and no verified trains found via division hubs or state capitals."
            ),
            "fallback_searches_count": searches_attempted,
            "latency_ms": round(elapsed_ms, 2),
        }
