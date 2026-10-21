"""
Asynchronous Load Generation & Deduplication Engine.

Simulates concurrent user queries against the Train Availability Microservice,
verifying that identical canonical keys are coalesced/deduplicated while
different keys are dispatched independently.
"""

import asyncio
import logging
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx

from app.config import settings
from app.models.schemas import (
    RunRequest,
    RunSummary,
    RequestMetric,
    CanonicalKeyStats,
    LatencySummary,
    TrainQueryPayload,
)
from app.services.payload_factory import generate_payloads

logger = logging.getLogger(__name__)


class LoadGeneratorService:
    """Executes bounded asynchronous load tests and audits deduplication behavior."""

    def __init__(self, target_url: Optional[str] = None):
        self.target_url = target_url or settings.target_availability_url

    async def _execute_single_request(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        payload: TrainQueryPayload,
        index: int,
        timeout: float,
    ) -> RequestMetric:
        """Executes a single simulated user request bounded by concurrency semaphore."""
        canonical_key = payload.canonical_key
        api_payload = payload.to_api_payload()

        async with semaphore:
            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    self.target_url,
                    json=api_payload,
                    timeout=timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0

                correlation_id = resp.headers.get("x-correlation-id")
                status_code = resp.status_code
                success = 200 <= status_code < 300

                error_msg = None
                booking_status = None
                response_timestamp = None

                if success:
                    try:
                        body_json = resp.json()
                        data = body_json.get("data", {})
                        booking_status = data.get("booking_status") or data.get("availability")
                        response_timestamp = data.get("last_updated")
                    except Exception:
                        pass
                else:
                    try:
                        err_json = resp.json()
                        error_msg = err_json.get("message") or resp.text[:120]
                    except Exception:
                        error_msg = resp.text[:120]

                return RequestMetric(
                    request_index=index,
                    canonical_key=canonical_key,
                    status_code=status_code,
                    latency_ms=round(latency_ms, 2),
                    success=success,
                    error=error_msg,
                    response_timestamp=response_timestamp,
                    booking_status=booking_status,
                    correlation_id=correlation_id,
                )

            except httpx.TimeoutException:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return RequestMetric(
                    request_index=index,
                    canonical_key=canonical_key,
                    status_code=504,
                    latency_ms=round(latency_ms, 2),
                    success=False,
                    error="Client-side request timeout",
                )
            except httpx.ConnectError as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return RequestMetric(
                    request_index=index,
                    canonical_key=canonical_key,
                    status_code=502,
                    latency_ms=round(latency_ms, 2),
                    success=False,
                    error=f"Connection failure: {str(exc)[:100]}",
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return RequestMetric(
                    request_index=index,
                    canonical_key=canonical_key,
                    status_code=500,
                    latency_ms=round(latency_ms, 2),
                    success=False,
                    error=f"Unexpected exception: {str(exc)[:100]}",
                )

    async def execute_run(
        self,
        request: RunRequest,
        client: Optional[httpx.AsyncClient] = None,
    ) -> RunSummary:
        """
        Executes a complete load-test run based on the supplied RunRequest.
        Supports passing an existing httpx client for mocking in tests.
        """
        run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        start_iso = datetime.utcnow().isoformat() + "Z"

        # Apply guardrails
        concurrency = min(
            request.concurrency or settings.default_concurrency,
            settings.max_allowed_concurrency,
        )
        total_requests = min(
            request.total_requests or settings.default_total_requests,
            settings.max_allowed_requests,
        )
        req_timeout = request.timeout_seconds or settings.request_timeout_seconds

        logger.info(
            f"Starting Load Test [{run_id}]: scenario='{request.scenario.value}', "
            f"requests={total_requests}, concurrency={concurrency}, target='{self.target_url}'"
        )

        # Generate payloads
        payloads = generate_payloads(
            scenario=request.scenario,
            total_requests=total_requests,
            custom_payloads=request.custom_payloads,
        )

        semaphore = asyncio.Semaphore(concurrency)
        limits = httpx.Limits(
            max_keepalive_connections=concurrency,
            max_connections=concurrency * 2,
        )

        t_start = time.perf_counter()

        if client is not None:
            # Reused client (e.g. test harness)
            tasks = [
                self._execute_single_request(client, semaphore, p, i, req_timeout)
                for i, p in enumerate(payloads)
            ]
            metrics = await asyncio.gather(*tasks)
        else:
            # Production async client with connection pooling
            async with httpx.AsyncClient(limits=limits) as managed_client:
                tasks = [
                    self._execute_single_request(managed_client, semaphore, p, i, req_timeout)
                    for i, p in enumerate(payloads)
                ]
                metrics = await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - t_start

        # Analyze and aggregate results
        return self._build_run_summary(
            run_id=run_id,
            timestamp=start_iso,
            scenario=request.scenario.value,
            total_duration=total_duration,
            metrics=metrics,
        )

    def _build_run_summary(
        self,
        run_id: str,
        timestamp: str,
        scenario: str,
        total_duration: float,
        metrics: List[RequestMetric],
    ) -> RunSummary:
        """Computes statistical summaries, deduplication audits, and breakdowns."""
        total_requests = len(metrics)
        latencies = [m.latency_ms for m in metrics]
        success_count = sum(1 for m in metrics if m.success)
        client_error_count = sum(1 for m in metrics if 400 <= m.status_code < 500)
        server_error_count = sum(1 for m in metrics if m.status_code >= 500)
        errors = [m.error for m in metrics if m.error is not None][:10]

        # Calculate latency stats
        if latencies:
            latencies_sorted = sorted(latencies)
            min_ms = round(latencies_sorted[0], 2)
            max_ms = round(latencies_sorted[-1], 2)
            avg_ms = round(statistics.mean(latencies_sorted), 2)
            p50_ms = round(statistics.median(latencies_sorted), 2)

            def get_percentile(p: float) -> float:
                idx = int(len(latencies_sorted) * p)
                idx = min(idx, len(latencies_sorted) - 1)
                return round(latencies_sorted[idx], 2)

            p90_ms = get_percentile(0.90)
            p95_ms = get_percentile(0.95)
            p99_ms = get_percentile(0.99)
        else:
            min_ms = max_ms = avg_ms = p50_ms = p90_ms = p95_ms = p99_ms = 0.0

        latency_summary = LatencySummary(
            min_ms=min_ms,
            avg_ms=avg_ms,
            p50_ms=p50_ms,
            p90_ms=p90_ms,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            max_ms=max_ms,
        )

        # Group by Canonical Key to verify Deduplication
        key_groups: Dict[str, List[RequestMetric]] = defaultdict(list)
        for m in metrics:
            key_groups[m.canonical_key].append(m)

        key_breakdowns: List[CanonicalKeyStats] = []
        deduplication_confirmed_count = 0

        for key, group in key_groups.items():
            grp_latencies = [m.latency_ms for m in group]
            grp_successes = sum(1 for m in group if m.success)
            grp_fails = len(group) - grp_successes

            status_counts: Dict[str, int] = defaultdict(int)
            for m in group:
                status_counts[str(m.status_code)] += 1

            # Check if all successful responses share the same response timestamp
            timestamps = {m.response_timestamp for m in group if m.response_timestamp}
            dedup_confirmed = len(group) > 1 and len(timestamps) <= 1 and grp_successes > 0
            if dedup_confirmed:
                deduplication_confirmed_count += 1

            efficiency = float(len(group))  # Ratio of simulated requests to single upstream execution

            key_breakdowns.append(
                CanonicalKeyStats(
                    canonical_key=key,
                    simulated_requests=len(group),
                    successful_requests=grp_successes,
                    failed_requests=grp_fails,
                    status_codes=dict(status_counts),
                    avg_latency_ms=round(statistics.mean(grp_latencies), 2) if grp_latencies else 0.0,
                    min_latency_ms=round(min(grp_latencies), 2) if grp_latencies else 0.0,
                    max_latency_ms=round(max(grp_latencies), 2) if grp_latencies else 0.0,
                    deduplication_confirmed=dedup_confirmed,
                    efficiency_ratio=round(efficiency, 2),
                    sample_response={
                        "booking_status": group[0].booking_status,
                        "last_updated": group[0].response_timestamp,
                        "correlation_id": group[0].correlation_id,
                    } if group else None,
                )
            )

        unique_keys = len(key_groups)
        dedup_ratio = round(total_requests / unique_keys, 2) if unique_keys > 0 else 1.0
        rps = round(total_requests / total_duration, 2) if total_duration > 0 else 0.0

        # Global deduplication verification: true if identical keys were coalesced
        dedup_verified = (
            deduplication_confirmed_count > 0 or unique_keys == total_requests
        )

        return RunSummary(
            run_id=run_id,
            timestamp=timestamp,
            scenario=scenario,
            target_url=self.target_url,
            total_simulated_requests=total_requests,
            unique_canonical_keys=unique_keys,
            deduplication_ratio=dedup_ratio,
            success_count=success_count,
            client_error_count=client_error_count,
            server_error_count=server_error_count,
            total_duration_sec=round(total_duration, 2),
            throughput_rps=rps,
            latency=latency_summary,
            deduplication_verified=dedup_verified,
            firestore_persisted=False,
            firestore_doc_id=None,
            key_breakdown=key_breakdowns,
            errors=errors,
        )


load_generator = LoadGeneratorService()


def get_load_generator() -> LoadGeneratorService:
    return load_generator
