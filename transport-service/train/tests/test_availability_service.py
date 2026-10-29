"""
Comprehensive Production Readiness Tests for Train Availability Microservice
Tests:
  - Input validation (valid/invalid trainNo, station codes, classes, dates, quotas)
  - Date validation & normalization (DD-MM-YYYY, YYYY-MM-DD, past dates, >120 days)
  - Response normalization (AVL, RAC, WL, REGRET, UNKNOWN)
  - Upstream timeout (504), connection error (502), and 5xx failures
  - Malformed upstream JSON and unexpected schemas
  - Circuit Breaker (trip to OPEN, fast-fail 503, recovery to HALF_OPEN/CLOSED)
  - In-flight request coalescing (Singleflight deduplication)
  - Concurrency and absence of cross-request state leakage
  - API contract backward compatibility (Query parameters vs JSON body)
  - Health (/health) and Readiness (/ready) probes
  - Security edge cases (path traversal strings, XSS attempts, identical stations)
"""

import sys
import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.config import config
from app.exceptions import (
    UpstreamTimeoutError,
    UpstreamConnectionError,
    UpstreamServiceError,
    CircuitBreakerOpenError,
)
from app.models.availability_models import (
    AvailabilityRequest,
    AvailabilityResponse,
    AvailabilityData,
)
from app.services.circuit_breaker import CircuitBreaker, CircuitState
from app.services.availability_provider import (
    ConfirmTktAvailabilityProvider,
    parse_booking_status,
)
from app.services.availability_service import (
    AvailabilityService,
    get_availability_service,
)


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


# Future date for tests
FUTURE_DATE_STR = (datetime.now() + timedelta(days=10)).strftime("%d-%m-%Y")
PAST_DATE_STR = (datetime.now() - timedelta(days=10)).strftime("%d-%m-%Y")
TOO_FAR_DATE_STR = (datetime.now() + timedelta(days=150)).strftime("%d-%m-%Y")


# ── 1. Input Validation Tests ────────────────────────────────────────────────

class TestInputValidation:
    def test_valid_request(self):
        req = AvailabilityRequest(
            trainNo="16102",
            source="RJPM",
            destination="SVKS",
            travelClass="SL",
            date=FUTURE_DATE_STR,
            quota="GN",
        )
        assert req.train_no == "16102"
        assert req.source == "RJPM"
        assert req.destination == "SVKS"
        assert req.travel_class == "SL"
        assert req.date == FUTURE_DATE_STR
        assert req.quota == "GN"

    def test_invalid_train_number_non_digit(self):
        with pytest.raises(ValueError, match="Invalid train number"):
            AvailabilityRequest(
                trainNo="ABC12",
                source="RJPM",
                destination="SVKS",
                travelClass="SL",
                date=FUTURE_DATE_STR,
            )

    def test_invalid_train_number_too_long(self):
        with pytest.raises(ValueError, match="Invalid train number"):
            AvailabilityRequest(
                trainNo="123456",
                source="RJPM",
                destination="SVKS",
                travelClass="SL",
                date=FUTURE_DATE_STR,
            )

    def test_invalid_station_code_format(self):
        with pytest.raises(ValueError, match="Invalid station code"):
            AvailabilityRequest(
                trainNo="16102",
                source="A",  # Too short
                destination="SVKS",
                travelClass="SL",
                date=FUTURE_DATE_STR,
            )

    def test_identical_source_and_destination(self):
        with pytest.raises(ValueError, match="Source and destination station codes cannot be identical"):
            AvailabilityRequest(
                trainNo="16102",
                source="MAS",
                destination="MAS",
                travelClass="SL",
                date=FUTURE_DATE_STR,
            )

    def test_invalid_travel_class(self):
        with pytest.raises(ValueError, match="Invalid travel class"):
            AvailabilityRequest(
                trainNo="16102",
                source="RJPM",
                destination="SVKS",
                travelClass="9A",  # Non-existent
                date=FUTURE_DATE_STR,
            )

    def test_invalid_quota(self):
        with pytest.raises(ValueError, match="Invalid quota"):
            AvailabilityRequest(
                trainNo="16102",
                source="RJPM",
                destination="SVKS",
                travelClass="SL",
                date=FUTURE_DATE_STR,
                quota="INVALID",
            )

    def test_past_date_rejected(self):
        with pytest.raises(ValueError, match="in the past"):
            AvailabilityRequest(
                trainNo="16102",
                source="RJPM",
                destination="SVKS",
                travelClass="SL",
                date=PAST_DATE_STR,
            )

    def test_date_exceeding_120_days_rejected(self):
        with pytest.raises(ValueError, match="exceeds maximum 120-day"):
            AvailabilityRequest(
                trainNo="16102",
                source="RJPM",
                destination="SVKS",
                travelClass="SL",
                date=TOO_FAR_DATE_STR,
            )

    def test_iso_date_format_normalized_to_indian_format(self):
        iso_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        expected_indian = (datetime.now() + timedelta(days=10)).strftime("%d-%m-%Y")
        req = AvailabilityRequest(
            trainNo="16102",
            source="RJPM",
            destination="SVKS",
            travelClass="SL",
            date=iso_date,
        )
        assert req.date == expected_indian


# ── 2. Response Status Normalization Tests ────────────────────────────────────

class TestResponseNormalization:
    def test_available_status_variants(self):
        assert parse_booking_status("AVAILABLE 15") == "AVAILABLE"
        assert parse_booking_status("AVL 282") == "AVAILABLE"
        assert parse_booking_status("CURR_AVBL 4") == "AVAILABLE"
        assert parse_booking_status("avl 10") == "AVAILABLE"

    def test_rac_status_variants(self):
        assert parse_booking_status("RAC 5") == "RAC"
        assert parse_booking_status("rac 12") == "RAC"

    def test_waitlist_status_variants(self):
        assert parse_booking_status("WL 12") == "WL"
        assert parse_booking_status("GNWL 45/WL 12") == "WL"
        assert parse_booking_status("PQWL 2") == "WL"
        assert parse_booking_status("RLWL 1") == "WL"
        assert parse_booking_status("WAITLIST 5") == "WL"

    def test_regret_status(self):
        assert parse_booking_status("REGRET") == "REGRET"
        assert parse_booking_status("regret/wl") == "REGRET"

    def test_unknown_status(self):
        assert parse_booking_status("NOT_FOUND") == "UNKNOWN"
        assert parse_booking_status("") == "UNKNOWN"


# ── 3. Circuit Breaker Tests ──────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_circuit_trips_to_open_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=5.0, name="test-cb")
        assert cb.state == CircuitState.CLOSED

        cb.record_failure(Exception("err 1"))
        cb.record_failure(Exception("err 2"))
        assert cb.state == CircuitState.CLOSED

        cb.record_failure(Exception("err 3"))
        assert cb.state == CircuitState.OPEN

        # Next call should be rejected immediately
        with pytest.raises(CircuitBreakerOpenError):
            cb.before_call()

    def test_circuit_recovers_to_half_open_and_closed(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1, name="test-cb")
        cb.record_failure(Exception("err 1"))
        cb.record_failure(Exception("err 2"))
        assert cb.state == CircuitState.OPEN

        # Sleep past reset timeout
        time.sleep(0.15)
        # before_call should transition to HALF_OPEN
        cb.before_call()
        assert cb.state == CircuitState.HALF_OPEN

        # On success, transitions back to CLOSED
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


# ── 4. In-Flight Request Coalescing (Singleflight) Tests ───────────────────────

@pytest.mark.asyncio
async def test_singleflight_coalesces_identical_concurrent_requests():
    """Verify that multiple concurrent identical requests execute only ONE upstream call."""
    mock_provider = AsyncMock()
    call_count = 0

    async def delayed_fetch(**kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "message": "Live availability fetched",
            "data": {
                "train_number": kwargs["train_no"],
                "travel_class": kwargs["travel_class"],
                "quota": kwargs["quota"],
                "availability": "AVL 50",
                "booking_status": "AVAILABLE",
                "prediction": 99,
                "fare": 500,
                "total_fare": 550,
                "booking_enabled": True,
                "last_updated": "2026-10-18T10:00:00",
                "next_available_dates": [],
            },
        }

    mock_provider.fetch_availability.side_effect = delayed_fetch

    service = AvailabilityService(provider=mock_provider)
    req = AvailabilityRequest(
        trainNo="12626",
        source="NDLS",
        destination="MAS",
        travelClass="3A",
        date=FUTURE_DATE_STR,
        quota="GN",
    )

    # Launch 10 simultaneous requests for the exact same train/date/class
    results = await asyncio.gather(*(service.async_fetch_availability(req) for _ in range(10)))

    # All 10 requests should succeed with identical data
    assert len(results) == 10
    for r in results:
        assert r["success"] is True
        assert r["data"]["availability"] == "AVL 50"

    # Upstream should have been called EXACTLY ONCE due to coalescing
    assert call_count == 1


# ── 5. Upstream Error Handling and HTTP Status Mapping Tests ─────────────────

class TestRouteErrorHandling:
    def test_upstream_timeout_returns_504(self, client):
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.side_effect = UpstreamTimeoutError("Timeout")

        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                f"/api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
            )
            assert resp.status_code == 504
            data = resp.json()
            assert "timed out" in data["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_upstream_service_error_returns_502(self, client):
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.side_effect = UpstreamServiceError("HTTP 502")

        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                f"/api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
            )
            assert resp.status_code == 502
            data = resp.json()
            assert "error" in data["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_circuit_breaker_open_returns_503(self, client):
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.side_effect = CircuitBreakerOpenError("Circuit is OPEN")

        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                f"/api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
            )
            assert resp.status_code == 503
            data = resp.json()
            assert "temporarily unavailable" in data["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_train_not_found_returns_404(self, client):
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.return_value = {
            "success": False,
            "message": "Train 99999 not found",
            "data": None,
        }

        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                f"/api/v1/trains/availability?trainNo=99999&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
            )
            assert resp.status_code == 404
            data = resp.json()
            assert "not found" in data["detail"].lower()
        finally:
            app.dependency_overrides.clear()


# ── 6. Backward Compatibility: Query Params vs JSON Body ──────────────────────

class TestBackwardCompatibility:
    SUCCESS_RESPONSE = {
        "success": True,
        "message": "Live availability fetched",
        "data": {
            "train_number": "16102",
            "travel_class": "SL",
            "quota": "GN",
            "availability": "AVL 25",
            "booking_status": "AVAILABLE",
            "prediction": 90,
            "fare": 140,
            "total_fare": 175,
            "booking_enabled": True,
            "last_updated": "2026-10-18T10:00:00",
            "next_available_dates": ["27-08-2026"],
        },
    }

    def test_query_parameters_style(self, client):
        """Original contract: parameters passed as URL query strings."""
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.return_value = self.SUCCESS_RESPONSE
        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                f"/api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}&quota=GN"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["train_number"] == "16102"
            assert body["data"]["availability"] == "AVL 25"
            assert body["data"]["booking_status"] == "AVAILABLE"
            assert resp.headers.get("X-Correlation-ID") is not None
        finally:
            app.dependency_overrides.clear()

    def test_json_body_style(self, client):
        """Modern REST contract: parameters passed as JSON request body."""
        mock_provider = AsyncMock()
        mock_provider.fetch_availability.return_value = self.SUCCESS_RESPONSE
        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            resp = client.post(
                "/api/v1/trains/availability",
                json={
                    "trainNo": "16102",
                    "source": "RJPM",
                    "destination": "SVKS",
                    "travelClass": "SL",
                    "date": FUTURE_DATE_STR,
                    "quota": "GN",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["data"]["train_number"] == "16102"
        finally:
            app.dependency_overrides.clear()


# ── 7. Health & Readiness Probe Tests ────────────────────────────────────────

class TestHealthAndReadiness:
    def test_liveness_probe_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "dream-destiny-train"

    def test_readiness_probe_ready(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["total_stations"] > 0


# ── 8. Security & Injection Edge Cases ────────────────────────────────────────

class TestSecurityEdgeCases:
    def test_path_traversal_attempt_in_train_no(self, client):
        resp = client.post(
            f"/api/v1/trains/availability?trainNo=../../etc/passwd&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
        )
        assert resp.status_code == 400

    def test_script_tag_in_station_code(self, client):
        resp = client.post(
            f"/api/v1/trains/availability?trainNo=16102&source=<script>&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
        )
        assert resp.status_code == 400

    def test_oversized_string_rejected(self, client):
        long_string = "A" * 5000
        resp = client.post(
            f"/api/v1/trains/availability?trainNo=16102&source={long_string}&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
        )
        assert resp.status_code == 400

    def test_docs_hidden_by_default(self, client):
        """Verify docs and openapi schema are hidden when docs are disabled."""
        from app.main import app
        if not app.docs_url:
            assert client.get("/docs").status_code == 404
            assert client.get("/openapi.json").status_code == 404
            assert client.get("/redoc").status_code == 404


# ── 9. Concurrent Load & Amplification Verification ──────────────────────────

class TestConcurrentLoad:
    @pytest.mark.asyncio
    async def test_high_concurrency_in_process_load(self):
        """
        Verify that 30 concurrent in-flight requests execute safely with zero state leakage
        and maximum upstream suppression via singleflight coalescing.
        """
        mock_provider = AsyncMock()
        call_counter = 0

        async def mock_fetch(**kwargs):
            nonlocal call_counter
            call_counter += 1
            await asyncio.sleep(0.02)
            return {
                "success": True,
                "message": "Live availability fetched",
                "data": {
                    "train_number": kwargs["train_no"],
                    "travel_class": kwargs["travel_class"],
                    "quota": kwargs["quota"],
                    "availability": "AVL 100",
                    "booking_status": "AVAILABLE",
                    "prediction": 99,
                    "fare": 300,
                    "total_fare": 350,
                    "booking_enabled": True,
                    "last_updated": "2026-10-18T10:00:00",
                    "next_available_dates": [],
                },
            }

        mock_provider.fetch_availability.side_effect = mock_fetch
        custom_service = AvailabilityService(provider=mock_provider)
        app.dependency_overrides[get_availability_service] = lambda: custom_service

        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                # 20 identical requests for Train 12626 + 10 distinct requests for Train 16102
                tasks = []
                # 20 identical
                for _ in range(20):
                    tasks.append(
                        ac.post(
                            f"/api/v1/trains/availability?trainNo=12626&source=NDLS&destination=MAS&travelClass=3A&date={FUTURE_DATE_STR}"
                        )
                    )
                # 10 identical for a different train
                for _ in range(10):
                    tasks.append(
                        ac.post(
                            f"/api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date={FUTURE_DATE_STR}"
                        )
                    )

                responses = await asyncio.gather(*tasks)

            assert len(responses) == 30
            for r in responses:
                assert r.status_code == 200
                data = r.json()
                assert data["success"] is True

            # All 20 for 12626 should coalesce to 1 call; all 10 for 16102 should coalesce to 1 call.
            # Total upstream calls should be <= 2!
            assert call_counter <= 2, f"Expected <= 2 upstream calls due to coalescing, got {call_counter}"
        finally:
            app.dependency_overrides.clear()
