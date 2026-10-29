"""
Unit & Integration Tests for Train Schedule Service and Endpoints
"""

import asyncio
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exceptions import (
    CircuitBreakerOpenError,
    InvalidRequestError,
    TrainNotFoundError,
    UpstreamConnectionError,
    UpstreamServiceError,
    UpstreamTimeoutError,
)
from app.main import app
from app.models.schedule_models import RouteStop, TrainScheduleData
from app.services.circuit_breaker import CircuitBreaker
from app.services.schedule_provider import (
    RedBusScheduleProvider,
    parse_distance_km,
    parse_halt_minutes,
)
from app.services.schedule_service import (
    ScheduleService,
    get_schedule_service,
)

SAMPLE_REDBUS_RAW_PAYLOAD = {
    "TrainName": "POTHIGAI SF EXP",
    "TrainNo": 12661,
    "TrainNumberString": "12661",
    "TrainType": "Superfast",
    "Source": "Chennai Egmore",
    "Destination": "Sengottai",
    "SourceCode": "MS",
    "DestinationCode": "SCT",
    "DaysOfRun": {
        "Mon": True,
        "Tue": True,
        "Wed": True,
        "Thu": True,
        "Fri": True,
        "Sat": True,
        "Sun": True,
    },
    "Classes": ["3A", "1A", "SL", "2A"],
    "TotalDuration": 665,
    "TotalDistance": "670 kms",
    "TotalNumberOfStops": "18",
    "Schedule": [
        {
            "StationName": "CHENNAI EGMORE",
            "StationCode": "MS",
            "StopNumber": 1,
            "ArrivalTime": "SOURCE",
            "DepartureTime": "19:35",
            "HaltMinutes": "0",
            "Day": 1,
            "DistanceFromOrigin": "0 kms",
            "ExpectedPlatformNo": "6",
        },
        {
            "StationName": "TAMBARAM",
            "StationCode": "TBM",
            "StopNumber": 2,
            "ArrivalTime": "20:00",
            "DepartureTime": "20:02",
            "HaltMinutes": "02:00",
            "Day": 1,
            "DistanceFromOrigin": "25 kms",
            "ExpectedPlatformNo": "7",
        },
        {
            "StationName": "TIRUCHCHIRAPALI",
            "StationCode": "TPJ",
            "StopNumber": 8,
            "ArrivalTime": "01:05",
            "DepartureTime": "01:10",
            "HaltMinutes": "05:00",
            "Day": 2,
            "DistanceFromOrigin": "336 kms",
            "ExpectedPlatformNo": "4",
        },
        {
            "StationName": "SENGOTTAI",
            "StationCode": "SCT",
            "StopNumber": 18,
            "ArrivalTime": "06:40",
            "DepartureTime": "DESTINATION",
            "HaltMinutes": "0",
            "Day": 2,
            "DistanceFromOrigin": "670 kms",
            "ExpectedPlatformNo": "1",
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_service_cache():
    """Ensures each test starts with a clean schedule cache."""
    service = get_schedule_service()
    service.clear_cache()
    yield
    service.clear_cache()


# ============================================================================
# 1. Parsing Helper Tests
# ============================================================================

def test_parse_halt_minutes():
    assert parse_halt_minutes("0") == 0
    assert parse_halt_minutes("00:00") == 0
    assert parse_halt_minutes("02:00") == 2
    assert parse_halt_minutes("05:00") == 5
    assert parse_halt_minutes("15:30") == 15
    assert parse_halt_minutes(10) == 10
    assert parse_halt_minutes("10") == 10
    assert parse_halt_minutes(None) == 0
    assert parse_halt_minutes("") == 0
    assert parse_halt_minutes("invalid") == 0


def test_parse_distance_km():
    assert parse_distance_km("0 kms") == 0
    assert parse_distance_km("25 kms") == 25
    assert parse_distance_km("336 kms") == 336
    assert parse_distance_km("1200 KMS") == 1200
    assert parse_distance_km(500) == 500
    assert parse_distance_km(None) == 0
    assert parse_distance_km("") == 0
    assert parse_distance_km("abc") == 0


# ============================================================================
# 2. Validation Tests
# ============================================================================

def test_validate_train_number_valid():
    assert ScheduleService.validate_train_number("12661") == "12661"
    assert ScheduleService.validate_train_number("02661") == "02661"
    assert ScheduleService.validate_train_number("1234") == "1234"
    assert ScheduleService.validate_train_number(" 12626 ") == "12626"


def test_validate_train_number_invalid():
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("")
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("123")  # too short
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("123456")  # too long
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("1266A")  # alphabetic
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("126 61")  # space
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number("1234; DROP TABLE")  # injection
    with pytest.raises(InvalidRequestError):
        ScheduleService.validate_train_number(None)  # None


# ============================================================================
# 3. Provider Payload Parsing Tests
# ============================================================================

def test_redbus_provider_parse_payload_success():
    provider = RedBusScheduleProvider()
    result = provider._parse_upstream_payload(SAMPLE_REDBUS_RAW_PAYLOAD, "12661")

    assert result["train_no"] == "12661"
    assert result["train_name"] == "POTHIGAI SF EXP"
    assert result["source_station_code"] == "MS"
    assert result["destination_station_code"] == "SCT"
    assert result["total_duration_minutes"] == 665
    assert result["total_distance_km"] == 670
    assert len(result["schedule"]) == 4

    # Verify origin SOURCE normalizer
    origin = result["schedule"][0]
    assert origin["station_code"] == "MS"
    assert origin["arrival_time"] == "19:35"
    assert origin["departure_time"] == "19:35"
    assert origin["halt_minutes"] == 0
    assert origin["expected_platform"] == "6"

    # Verify intermediate stop
    tpj = result["schedule"][2]
    assert tpj["station_code"] == "TPJ"
    assert tpj["arrival_time"] == "01:05"
    assert tpj["departure_time"] == "01:10"
    assert tpj["halt_minutes"] == 5
    assert tpj["day"] == 2
    assert tpj["distance_from_origin_km"] == 336

    # Verify destination DESTINATION normalizer
    dest = result["schedule"][3]
    assert dest["station_code"] == "SCT"
    assert dest["arrival_time"] == "06:40"
    assert dest["departure_time"] == "06:40"
    assert dest["halt_minutes"] == 0


def test_redbus_provider_parse_payload_train_not_found():
    provider = RedBusScheduleProvider()

    # RedBus 417 error payload
    err_payload = {
        "success": False,
        "data": {
            "status": 417,
            "statusText": "Expectation Failed",
            "data": {"errorcode": "114", "errormsg": "Unable to fetch the train schedule"},
        },
    }
    with pytest.raises(TrainNotFoundError):
        provider._parse_upstream_payload(err_payload, "99999")

    # Empty schedule
    with pytest.raises(TrainNotFoundError):
        provider._parse_upstream_payload({"Schedule": []}, "99999")


# ============================================================================
# 4. ScheduleService Caching & Singleflight Concurrency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_schedule_service_cache_hit():
    mock_provider = AsyncMock()
    mock_provider.fetch_schedule.return_value = RedBusScheduleProvider()._parse_upstream_payload(
        SAMPLE_REDBUS_RAW_PAYLOAD, "12661"
    )

    service = ScheduleService(provider=mock_provider, cache_ttl=3600)

    # First call: hits provider
    res1 = await service.get_schedule("12661")
    assert res1.train_name == "POTHIGAI SF EXP"
    assert mock_provider.fetch_schedule.call_count == 1

    # Second call: hits in-memory TTL cache (sub-millisecond)
    res2 = await service.get_schedule("12661")
    assert res2.train_name == "POTHIGAI SF EXP"
    assert mock_provider.fetch_schedule.call_count == 1  # Unchanged!


@pytest.mark.asyncio
async def test_schedule_service_singleflight_coalescing():
    """
    Simulates 10 concurrent requests arriving simultaneously for the same train.
    Verifies only 1 upstream request is dispatched and all 10 callers resolve with the same result.
    """
    call_counter = 0

    async def slow_fetch(train_no: str) -> Dict[str, Any]:
        nonlocal call_counter
        call_counter += 1
        await asyncio.sleep(0.05)  # Simulate network latency
        return RedBusScheduleProvider()._parse_upstream_payload(SAMPLE_REDBUS_RAW_PAYLOAD, train_no)

    mock_provider = AsyncMock()
    mock_provider.fetch_schedule.side_effect = slow_fetch

    service = ScheduleService(provider=mock_provider, cache_ttl=0)  # TTL=0 to strictly test coalescer

    # Fire 10 simultaneous tasks
    tasks = [service.get_schedule("12661") for _ in range(10)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 10
    for res in results:
        assert res.train_no == "12661"
        assert res.train_name == "POTHIGAI SF EXP"

    # Only 1 single call dispatched to upstream provider!
    assert call_counter == 1


@pytest.mark.asyncio
async def test_schedule_service_upstream_exceptions():
    mock_provider = AsyncMock()
    mock_provider.fetch_schedule.side_effect = UpstreamTimeoutError("Timeout")
    service = ScheduleService(provider=mock_provider)

    with pytest.raises(UpstreamTimeoutError):
        await service.get_schedule("12661")

    mock_provider.fetch_schedule.side_effect = UpstreamConnectionError("Connect failed")
    with pytest.raises(UpstreamConnectionError):
        await service.get_schedule("12661")

    mock_provider.fetch_schedule.side_effect = TrainNotFoundError("Train 99999 not found")
    with pytest.raises(TrainNotFoundError):
        await service.get_schedule("99999")


# ============================================================================
# 5. FastAPI Endpoints Integration Tests (TestClient)
# ============================================================================

def test_api_schedule_path_param_success():
    client = TestClient(app)
    mock_data = RedBusScheduleProvider()._parse_upstream_payload(SAMPLE_REDBUS_RAW_PAYLOAD, "12661")

    with patch.object(RedBusScheduleProvider, "fetch_schedule", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        response = client.get("/api/v1/trains/12661/schedule")

        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "max-age=86400" in response.headers["Cache-Control"]
        assert "stale-while-revalidate" in response.headers["Cache-Control"]
        json_resp = response.json()
        assert json_resp["success"] is True
        assert json_resp["data"]["train_no"] == "12661"
        assert json_resp["data"]["train_name"] == "POTHIGAI SF EXP"
        assert len(json_resp["data"]["schedule"]) == 4


def test_api_schedule_query_param_success():
    client = TestClient(app)
    mock_data = RedBusScheduleProvider()._parse_upstream_payload(SAMPLE_REDBUS_RAW_PAYLOAD, "12661")

    with patch.object(RedBusScheduleProvider, "fetch_schedule", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data

        # Test trainNo query param
        resp1 = client.get("/api/v1/trains/schedule?trainNo=12661")
        assert resp1.status_code == 200
        assert "max-age=86400" in resp1.headers.get("Cache-Control", "")
        assert resp1.json()["data"]["train_no"] == "12661"

        # Test train_no snake_case query param
        resp2 = client.get("/api/v1/trains/schedule?train_no=12661")
        assert resp2.status_code == 200
        assert "max-age=86400" in resp2.headers.get("Cache-Control", "")
        assert resp2.json()["data"]["train_no"] == "12661"


def test_api_schedule_missing_query_param():
    client = TestClient(app)
    response = client.get("/api/v1/trains/schedule")
    assert response.status_code == 400
    assert "required" in response.json()["message"].lower()


def test_api_schedule_invalid_train_format():
    client = TestClient(app)
    response = client.get("/api/v1/trains/abc/schedule")
    assert response.status_code == 400
    assert "invalid train number" in response.json()["message"].lower()


def test_api_schedule_train_not_found():
    client = TestClient(app)
    with patch.object(RedBusScheduleProvider, "fetch_schedule", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = TrainNotFoundError("Train 99999 not found or schedule unavailable")
        response = client.get("/api/v1/trains/99999/schedule")

        assert response.status_code == 404
        assert response.json()["success"] is False
        assert "not found" in response.json()["message"].lower()


def test_api_schedule_upstream_timeout():
    client = TestClient(app)
    with patch.object(RedBusScheduleProvider, "fetch_schedule", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = UpstreamTimeoutError("Timeout")
        response = client.get("/api/v1/trains/12661/schedule")

        assert response.status_code == 504
        assert response.json()["success"] is False


def test_api_schedule_circuit_breaker_open():
    client = TestClient(app)
    with patch.object(RedBusScheduleProvider, "fetch_schedule", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = CircuitBreakerOpenError("Circuit open")
        response = client.get("/api/v1/trains/12661/schedule")

        assert response.status_code == 503
        assert response.json()["success"] is False
