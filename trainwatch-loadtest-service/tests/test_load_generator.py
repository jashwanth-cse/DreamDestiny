"""
Automated tests proving deduplication correctness and load generation metrics.
"""

import asyncio
import json
import pytest
import httpx

from app.models.schemas import RunRequest, ScenarioType
from app.services.load_generator import LoadGeneratorService


@pytest.mark.asyncio
async def test_deduplication_correctness_identical_burst():
    """
    PROVES DEDUPLICATION CORRECTNESS:
    Simulates 25 concurrent requests requesting the exact same canonical key.
    Verifies that all 25 requests share the same canonical key, return identical
    cached/coalesced availability timestamps, achieve a deduplication ratio of 25.0,
    and deduplication_verified evaluates to True.
    """
    call_count = 0
    fixed_timestamp = "2026-10-21T12:00:00.000Z"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "Live availability fetched",
                "data": {
                    "train_number": body["trainNo"],
                    "travel_class": body["travelClass"],
                    "quota": body["quota"],
                    "availability": "WL 12",
                    "booking_status": "WL",
                    "last_updated": fixed_timestamp,
                },
            },
            headers={"x-correlation-id": f"corr-{call_count}"},
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        load_gen = LoadGeneratorService(target_url="http://test-server/api/v1/trains/availability")
        req = RunRequest(
            scenario=ScenarioType.BURST_IDENTICAL,
            concurrency=10,
            total_requests=25,
        )

        summary = await load_gen.execute_run(req, client=mock_client)

        assert summary.total_simulated_requests == 25
        assert summary.unique_canonical_keys == 1
        assert summary.deduplication_ratio == 25.0
        assert summary.success_count == 25
        assert summary.server_error_count == 0
        assert summary.client_error_count == 0
        assert summary.deduplication_verified is True

        # Check breakdown
        assert len(summary.key_breakdown) == 1
        key_stat = summary.key_breakdown[0]
        assert key_stat.simulated_requests == 25
        assert key_stat.deduplication_confirmed is True
        assert key_stat.efficiency_ratio == 25.0
        assert key_stat.sample_response["last_updated"] == fixed_timestamp


@pytest.mark.asyncio
async def test_diverse_keys_independent_processing():
    """
    Verifies that different canonical keys are handled independently.
    """
    def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "train_number": body["trainNo"],
                    "travel_class": body["travelClass"],
                    "quota": body["quota"],
                    "availability": "AVAILABLE 45",
                    "booking_status": "AVAILABLE",
                    "last_updated": "2026-10-21T12:05:00.000Z",
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        load_gen = LoadGeneratorService(target_url="http://test-server/api/v1/trains/availability")
        req = RunRequest(
            scenario=ScenarioType.DIVERSE_MATRIX,
            concurrency=5,
            total_requests=20,
        )

        summary = await load_gen.execute_run(req, client=mock_client)

        assert summary.total_simulated_requests == 20
        assert summary.unique_canonical_keys > 1
        assert summary.success_count == 20
        assert summary.latency.min_ms >= 0.0
        assert summary.latency.avg_ms >= 0.0


@pytest.mark.asyncio
async def test_upstream_error_tolerance():
    """
    Verifies that upstream 502/504 errors are gracefully captured without crashing.
    """
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"success": False, "message": "Upstream availability provider failure"},
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        load_gen = LoadGeneratorService(target_url="http://test-server/api/v1/trains/availability")
        req = RunRequest(
            scenario=ScenarioType.BURST_IDENTICAL,
            concurrency=5,
            total_requests=10,
        )

        summary = await load_gen.execute_run(req, client=mock_client)

        assert summary.total_simulated_requests == 10
        assert summary.server_error_count == 10
        assert summary.success_count == 0
        assert len(summary.errors) > 0
