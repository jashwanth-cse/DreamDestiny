"""
Comprehensive Tests for RouteFallbackService, DivisionResolver, and StateCapitalResolver.

Covers all test requirements in plan.md Section 8:
  - station -> division resolution
  - division -> hub resolution
  - station -> state resolution
  - state -> capital station resolution
  - direct train available (Level 1 returns immediately)
  - no direct train -> division fallback (Level 2)
  - division fallback unavailable -> state-capital fallback (Level 3)
  - no fallback available (all yield 0 trains -> no_route_found)
  - train API error must NOT trigger fallback (must re-raise)
  - duplicate route prevention (skips division/capital if identical to previous)
  - correct fallback metadata (original_source, actual_source, fallback_reason, route_type)
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.resolver.division_resolver import DivisionResolver
from app.resolver.railway_station_resolver import RailwayStationResolver, ResolveStatus, StationMatch
from app.resolver.state_capital_resolver import StateCapitalResolver
from app.services.route_fallback_service import RouteFallbackService
from app.services.station_service import StationService


# ── Fixtures & Mock Data ──────────────────────────────────────────────────────

SAMPLE_STATIONS = {
    "RJPM": {
        "station_code": "RJPM",
        "station_name": "Rajapalayam",
        "division": "MDU",
        "zone": "SR",
        "district": "VIRUDHUNAGAR",
        "state": "TAMIL NADU",
    },
    "MDU": {
        "station_code": "MDU",
        "station_name": "Madurai Jn",
        "division": "MDU",
        "zone": "SR",
        "district": "MADURAI",
        "state": "TAMIL NADU",
    },
    "MAS": {
        "station_code": "MAS",
        "station_name": "MGR Chennai Central",
        "division": "MAS",
        "zone": "SR",
        "district": "CHENNAI",
        "state": "TAMIL NADU",
    },
    "NDLS": {
        "station_code": "NDLS",
        "station_name": "New Delhi",
        "division": "DLI",
        "zone": "NR",
        "district": "NEW DELHI",
        "state": "DELHI",
    },
    "AGC": {
        "station_code": "AGC",
        "station_name": "Agra Cantt",
        "division": "AGRA",
        "zone": "NCR",
        "district": "AGRA",
        "state": "UTTAR PRADESH",
    },
    "LKO": {
        "station_code": "LKO",
        "station_name": "Lucknow Charbagh",
        "division": "LKO",
        "zone": "NR",
        "district": "LUCKNOW",
        "state": "UTTAR PRADESH",
    },
}

SAMPLE_DIVISION_HUBS = {
    "MDU": {"division": "MDU", "hub_code": "MDU", "hub_name": "Madurai Jn", "zone": "SR"},
    "MAS": {"division": "MAS", "hub_code": "MAS", "hub_name": "MGR Chennai Central", "zone": "SR"},
    "DLI": {"division": "DLI", "hub_code": "NDLS", "hub_name": "New Delhi", "zone": "NR"},
    "AGRA": {"division": "AGRA", "hub_code": "AGC", "hub_name": "Agra Cantt", "zone": "NCR"},
    "LKO": {"division": "LKO", "hub_code": "LKO", "hub_name": "Lucknow Charbagh", "zone": "NR"},
}

SAMPLE_STATE_CAPITALS = {
    "TAMIL NADU": {"capital": "Chennai", "station_code": "MAS", "station_name": "MGR Chennai Central"},
    "DELHI": {"capital": "New Delhi", "station_code": "NDLS", "station_name": "New Delhi"},
    "UTTAR PRADESH": {"capital": "Lucknow", "station_code": "LKO", "station_name": "Lucknow Charbagh"},
}


def _dummy_train(num: str = "12662", name: str = "Test Express") -> Dict[str, Any]:
    return {
        "train_number": num,
        "train_name": name,
        "train_type": "EXP",
        "from": {"code": "A", "name": "Station A"},
        "to": {"code": "B", "name": "Station B"},
        "departure_time": "10:00",
        "arrival_time": "12:00",
        "duration_minutes": 120,
        "duration": "2h 0m",
        "distance": 100,
        "running_days": ["Mon", "Tue"],
        "rating": 4.5,
        "has_pantry": True,
        "lowest_fare": 300,
        "classes": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. DivisionResolver Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDivisionResolver:
    @pytest.fixture
    def resolver(self):
        stn_resolver = MagicMock()
        stn_resolver.get_by_code.side_effect = lambda c: SAMPLE_STATIONS.get(c)
        div_res = DivisionResolver(station_resolver=stn_resolver)
        div_res._hubs = SAMPLE_DIVISION_HUBS
        div_res._loaded = True
        return div_res

    def test_division_to_hub_resolution(self, resolver):
        hub = resolver.get_hub_by_division("MDU")
        assert hub is not None
        assert hub["station_code"] == "MDU"
        assert hub["station_name"] == "Madurai Jn"

    def test_station_dict_to_hub_resolution(self, resolver):
        rjpm = SAMPLE_STATIONS["RJPM"]
        hub = resolver.get_hub(rjpm)
        assert hub is not None
        assert hub["station_code"] == "MDU"

    def test_unknown_division_returns_none(self, resolver):
        assert resolver.get_hub_by_division("UNKNOWN_DIV") is None

    def test_station_without_division_returns_none(self, resolver):
        assert resolver.get_hub({"station_name": "Test", "station_code": "TST"}) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. StateCapitalResolver Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStateCapitalResolver:
    @pytest.fixture
    def resolver(self):
        stn_resolver = MagicMock()
        stn_resolver.get_by_code.side_effect = lambda c: SAMPLE_STATIONS.get(c)
        cap_res = StateCapitalResolver(station_resolver=stn_resolver)
        cap_res._capitals = SAMPLE_STATE_CAPITALS
        cap_res._loaded = True
        return cap_res

    def test_state_to_capital_resolution(self, resolver):
        cap = resolver.get_capital_by_state("TAMIL NADU")
        assert cap is not None
        assert cap["station_code"] == "MAS"
        assert cap["station_name"] == "MGR Chennai Central"

    def test_station_dict_to_capital_resolution(self, resolver):
        rjpm = SAMPLE_STATIONS["RJPM"]
        cap = resolver.get_capital(rjpm)
        assert cap is not None
        assert cap["station_code"] == "MAS"

    def test_unknown_state_returns_none(self, resolver):
        assert resolver.get_capital_by_state("UNKNOWN_STATE") is None

    def test_case_insensitive_matching(self, resolver):
        assert resolver.get_capital_by_state("tamil nadu")["station_code"] == "MAS"


# ─────────────────────────────────────────────────────────────────────────────
# 3. RouteFallbackService Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRouteFallbackService:
    @pytest.fixture
    def setup_service(self):
        station_service = MagicMock(spec=StationService)
        # Mock get_station
        station_service.get_station.side_effect = lambda q: (
            SAMPLE_STATIONS.get(q.upper()) or SAMPLE_STATIONS.get(
                {"rajapalayam": "RJPM", "agra": "AGC", "delhi": "NDLS", "madurai": "MDU"}.get(q.lower(), "RJPM")
            )
        )

        stn_resolver = MagicMock()
        stn_resolver.get_by_code.side_effect = lambda c: SAMPLE_STATIONS.get(c)

        div_res = DivisionResolver(station_resolver=stn_resolver)
        div_res._hubs = SAMPLE_DIVISION_HUBS
        div_res._loaded = True

        cap_res = StateCapitalResolver(station_resolver=stn_resolver)
        cap_res._capitals = SAMPLE_STATE_CAPITALS
        cap_res._loaded = True

        train_service = MagicMock()

        fallback_svc = RouteFallbackService(
            station_service=station_service,
            division_resolver=div_res,
            state_capital_resolver=cap_res,
            train_service=train_service,
        )
        return fallback_svc, train_service

    def test_direct_train_available(self, setup_service):
        """When Level 1 direct search returns trains, return immediately with direct route_type."""
        svc, train_svc = setup_service
        train_svc.search_direct.return_value = {
            "result_type": "direct",
            "source": "Rajapalayam",
            "destination": "New Delhi",
            "total_trains": 1,
            "trains": [_dummy_train()],
        }

        res = svc.search_with_fallback("Rajapalayam", "Delhi", "20-11-2026")

        assert res["route_type"] == "direct"
        assert res["fallback_searches_count"] == 1
        assert res["fallback_reason"] is None
        assert res["actual_source"]["station_code"] == "RJPM"
        assert res["actual_destination"]["station_code"] == "NDLS"
        assert len(res["trains"]) == 1
        assert train_svc.search_direct.call_count == 1

    def test_no_direct_train_triggers_division_fallback(self, setup_service):
        """When Level 1 returns 0 trains, search division hubs (RJPM->MDU, Delhi->NDLS)."""
        svc, train_svc = setup_service

        # First call (direct RJPM->NDLS) returns 0 trains; second call (MDU->NDLS) returns 2 trains
        train_svc.search_direct.side_effect = [
            {"result_type": "direct", "source": "RJPM", "destination": "NDLS", "total_trains": 0, "trains": []},
            {"result_type": "direct", "source": "MDU", "destination": "NDLS", "total_trains": 2, "trains": [_dummy_train("12651"), _dummy_train("12652")]},
        ]

        res = svc.search_with_fallback("Rajapalayam", "Delhi", "20-11-2026")

        assert res["route_type"] == "division_fallback"
        assert res["fallback_searches_count"] == 2
        assert "division hubs" in res["fallback_reason"]
        assert res["original_source"]["station_code"] == "RJPM"
        assert res["actual_source"]["station_code"] == "MDU"
        assert res["actual_destination"]["station_code"] == "NDLS"
        assert len(res["trains"]) == 2
        assert train_svc.search_direct.call_count == 2

    def test_division_fails_triggers_state_capital_fallback(self, setup_service):
        """When Level 1 and Level 2 both return 0 trains, fallback to state capitals (MAS->NDLS)."""
        svc, train_svc = setup_service

        # Level 1 returns [], Level 2 returns [], Level 3 returns 1 train
        train_svc.search_direct.side_effect = [
            {"result_type": "direct", "total_trains": 0, "trains": []},  # RJPM -> NDLS
            {"result_type": "direct", "total_trains": 0, "trains": []},  # MDU -> NDLS (division)
            {"result_type": "direct", "total_trains": 1, "trains": [_dummy_train("12615", "Grand Trunk Exp")]},  # MAS -> NDLS (capital)
        ]

        res = svc.search_with_fallback("Rajapalayam", "Delhi", "20-11-2026")

        assert res["route_type"] == "state_capital_fallback"
        assert res["fallback_searches_count"] == 3
        assert "state capitals" in res["fallback_reason"]
        assert res["original_source"]["station_code"] == "RJPM"
        assert res["actual_source"]["station_code"] == "MAS"
        assert res["actual_destination"]["station_code"] == "NDLS"
        assert len(res["trains"]) == 1

    def test_no_fallback_available_returns_no_route_found(self, setup_service):
        """When all levels return 0 trains, cleanly return route_type='no_route_found'."""
        svc, train_svc = setup_service

        # All 3 levels return 0 trains
        train_svc.search_direct.side_effect = [
            {"result_type": "direct", "total_trains": 0, "trains": []},
            {"result_type": "direct", "total_trains": 0, "trains": []},
            {"result_type": "direct", "total_trains": 0, "trains": []},
        ]

        res = svc.search_with_fallback("Rajapalayam", "Delhi", "20-11-2026")

        assert res["route_type"] == "no_route_found"
        assert res["total_trains"] == 0
        assert res["trains"] == []
        assert "no verified trains found" in res["fallback_reason"]
        assert res["fallback_searches_count"] == 3

    def test_train_api_error_must_not_trigger_fallback(self, setup_service):
        """An API error or timeout during Level 1 must re-raise and NEVER trigger fallback."""
        svc, train_svc = setup_service

        train_svc.search_direct.side_effect = Exception("Ixigo API Timeout")

        with pytest.raises(Exception, match="Ixigo API Timeout"):
            svc.search_with_fallback("Rajapalayam", "Delhi", "20-11-2026")

        # Must have only attempted the direct route once, never proceeded to division/capital
        assert train_svc.search_direct.call_count == 1

    def test_duplicate_route_prevention(self, setup_service):
        """If division hubs or state capitals match the direct route, do not query them again."""
        svc, train_svc = setup_service

        # Source is Madurai (MDU) which is ALREADY its division hub!
        # Destination is New Delhi (NDLS) which is ALREADY its division hub and state capital!
        # Level 1: MDU -> NDLS (0 trains)
        # Level 2: Division is MDU -> NDLS (identical to Level 1, skipped!)
        # Level 3: Capital is MAS -> NDLS (distinct, attempted!)
        train_svc.search_direct.side_effect = [
            {"result_type": "direct", "total_trains": 0, "trains": []},  # Level 1: MDU -> NDLS
            {"result_type": "direct", "total_trains": 1, "trains": [_dummy_train("12621")]},  # Level 3: MAS -> NDLS
        ]

        res = svc.search_with_fallback("MDU", "NDLS", "20-11-2026")

        # Level 2 was skipped because MDU->NDLS is identical to Level 1
        assert res["route_type"] == "state_capital_fallback"
        assert res["fallback_searches_count"] == 2
        assert train_svc.search_direct.call_count == 2
