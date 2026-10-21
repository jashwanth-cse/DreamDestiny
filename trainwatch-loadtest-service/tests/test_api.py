"""
API Endpoint Integration Tests.
"""

import asyncio
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app, _run_lock
from app.config import settings
from app.models.schemas import RunSummary, LatencySummary


def dummy_run_summary():
    return RunSummary(
        run_id="run_test_123",
        timestamp="2026-10-21T12:00:00Z",
        scenario="balanced",
        target_url="http://test-server",
        total_simulated_requests=10,
        unique_canonical_keys=5,
        deduplication_ratio=2.0,
        success_count=10,
        client_error_count=0,
        server_error_count=0,
        total_duration_sec=0.5,
        throughput_rps=20.0,
        latency=LatencySummary(
            min_ms=10.0, avg_ms=15.0, p50_ms=14.0, p90_ms=18.0, p95_ms=19.0, p99_ms=20.0, max_ms=20.0
        ),
        deduplication_verified=True,
        firestore_persisted=False,
        key_breakdown=[],
        errors=[],
    )


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trainwatch-loadtest-service"
    assert data["version"] == "1.0.0"


def test_run_endpoint_success(client: TestClient):
    with patch("app.main.check_blackout_window", return_value=(False, None)), patch(
        "app.services.load_generator.LoadGeneratorService.execute_run",
        return_value=dummy_run_summary(),
    ):
        response = client.post(
            "/run",
            json={"scenario": "balanced", "concurrency": 2, "total_requests": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run_test_123"
        assert data["total_simulated_requests"] == 10
        assert data["deduplication_verified"] is True


def test_overlapping_runs_rejected_with_409(client: TestClient):
    """
    PREVENTS OVERLAPPING RUNS:
    If a test run is actively executing (lock acquired), incoming /run requests
    must be immediately rejected with 409 Conflict.
    """
    async def acquire_lock():
        await _run_lock.acquire()

    asyncio.run(acquire_lock())
    try:
        with patch("app.main.check_blackout_window", return_value=(False, None)):
            response = client.post("/run", json={"scenario": "balanced"})
            assert response.status_code == 409
            data = response.json()
            assert data["success"] is False
            assert "in progress" in data["message"]
    finally:
        _run_lock.release()


def test_api_key_authorization(client: TestClient):
    original_key = settings.service_api_key
    try:
        settings.service_api_key = "secret-test-token"

        # Missing auth header -> 401
        res1 = client.post("/run", json={"scenario": "balanced"})
        assert res1.status_code == 401

        # Invalid auth header -> 401
        res2 = client.post(
            "/run",
            headers={"X-API-Key": "wrong-token"},
            json={"scenario": "balanced"},
        )
        assert res2.status_code == 401

        # Valid X-API-Key header -> 200
        with patch(
            "app.services.load_generator.LoadGeneratorService.execute_run",
            return_value=dummy_run_summary(),
        ):
            res3 = client.post(
                "/run",
                headers={"X-API-Key": "secret-test-token"},
                json={"scenario": "balanced"},
            )
            assert res3.status_code == 200

            # Valid Bearer Authorization header -> 200
            res4 = client.post(
                "/run",
                headers={"Authorization": "Bearer secret-test-token"},
                json={"scenario": "balanced"},
            )
            assert res4.status_code == 200

    finally:
        settings.service_api_key = original_key


def test_list_and_get_runs(client: TestClient):
    # Save a run to fallback storage
    from app.services.firestore_storage import get_firestore_storage
    storage = get_firestore_storage()
    dummy = dummy_run_summary()
    asyncio.run(storage.save_run(dummy))

    res_list = client.get("/runs?limit=5")
    assert res_list.status_code == 200
    runs = res_list.json()
    assert isinstance(runs, list)
    assert any(r["run_id"] == "run_test_123" for r in runs)

    res_single = client.get("/runs/run_test_123")
    assert res_single.status_code == 200
    assert res_single.json()["run_id"] == "run_test_123"

    res_404 = client.get("/runs/non_existent_id")
    assert res_404.status_code == 404
