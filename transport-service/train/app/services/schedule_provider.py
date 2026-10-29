"""
Train Schedule Provider Protocol & RedBus Implementation

Provides non-blocking, resilient upstream access to train schedules with:
  - Connection pooling via httpx.AsyncClient (HTTP/2 enabled)
  - Circuit Breaker integration
  - Exponential backoff with jitter on transient failures
  - Defensive parsing and data normalization
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import httpx

from app.config import config
from app.exceptions import (
    CircuitBreakerOpenError,
    TrainNotFoundError,
    UpstreamConnectionError,
    UpstreamServiceError,
    UpstreamTimeoutError,
)
from app.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


def parse_halt_minutes(raw: Any) -> int:
    """Parses halt duration strings like '02:00', '05:00', '0', 5 into integer minutes."""
    if raw is None:
        return 0
    raw_str = str(raw).strip()
    if not raw_str or raw_str == "0":
        return 0
    if ":" in raw_str:
        try:
            parts = raw_str.split(":")
            return int(parts[0])
        except (ValueError, IndexError):
            return 0
    try:
        return int(raw_str)
    except ValueError:
        return 0


def parse_distance_km(raw: Any) -> int:
    """Parses distance strings like '336 kms', '0 kms', 336 into integer kilometers."""
    if raw is None:
        return 0
    raw_str = str(raw).strip()
    match = re.search(r"(\d+)", raw_str)
    if match:
        return int(match.group(1))
    return 0


@runtime_checkable
class ScheduleProvider(Protocol):
    """Abstract interface for train schedule providers."""

    async def fetch_schedule(self, train_no: str) -> Dict[str, Any]:
        """Fetch normalized schedule data for a given train number."""
        ...

    async def aclose(self) -> None:
        """Release underlying HTTP client resources."""
        ...


class RedBusScheduleProvider:
    """
    Production-grade RedBus/redRail train schedule provider.
    Uses non-blocking httpx.AsyncClient with HTTP/2 and Circuit Breaker.
    """

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self.url = config.SCHEDULE_API
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            reset_timeout=config.CIRCUIT_BREAKER_RESET_TIMEOUT,
            name="redbus-schedule",
        )

        timeout = httpx.Timeout(
            connect=config.CONNECT_TIMEOUT,
            read=config.READ_TIMEOUT,
            write=config.WRITE_TIMEOUT,
            pool=config.POOL_TIMEOUT,
        )
        limits = httpx.Limits(
            max_keepalive_connections=config.MAX_KEEPALIVE_CONNECTIONS,
            max_connections=config.MAX_CONNECTIONS,
        )
        if client is not None:
            self._client = client
        else:
            try:
                self._client = httpx.AsyncClient(http2=True, timeout=timeout, limits=limits)
            except (ImportError, RuntimeError, Exception) as exc:
                logger.warning(f"HTTP/2 client creation failed ({exc}), falling back to standard HTTP/1.1 client")
                self._client = httpx.AsyncClient(timeout=timeout, limits=limits)

    def _parse_upstream_payload(self, raw_data: Dict[str, Any], train_no: str) -> Dict[str, Any]:
        """Defensively parse and normalize raw RedBus schedule JSON."""
        # Detect RedBus error envelope
        if not raw_data.get("Schedule") and (
            raw_data.get("data", {}).get("status") == 417
            or raw_data.get("data", {}).get("data", {}).get("errorcode") == "114"
        ):
            raise TrainNotFoundError(f"Train {train_no} not found or schedule unavailable")

        raw_stops = raw_data.get("Schedule")
        if not raw_stops or not isinstance(raw_stops, list):
            raise TrainNotFoundError(f"No route schedule found for train {train_no}")

        normalized_stops: List[Dict[str, Any]] = []
        for idx, stop in enumerate(raw_stops, start=1):
            if not isinstance(stop, dict):
                continue

            arr = str(stop.get("ArrivalTime", "")).strip()
            dep = str(stop.get("DepartureTime", "")).strip()

            # Handle origin and destination string sentinels
            if arr.upper() == "SOURCE":
                arr = dep
            if dep.upper() == "DESTINATION":
                dep = arr

            halt_mins = parse_halt_minutes(stop.get("HaltMinutes"))
            dist_km = parse_distance_km(stop.get("DistanceFromOrigin"))
            platform = stop.get("ExpectedPlatformNo")
            if platform in ("NA", "0", "", None):
                platform = None
            else:
                platform = str(platform).strip()

            normalized_stops.append({
                "stop_number": int(stop.get("StopNumber", idx)),
                "station_name": str(stop.get("StationName", "")).strip(),
                "station_code": str(stop.get("StationCode", "")).strip().upper(),
                "arrival_time": arr,
                "departure_time": dep,
                "halt_minutes": halt_mins,
                "day": int(stop.get("Day", 1)),
                "distance_from_origin_km": dist_km,
                "expected_platform": platform,
            })

        if not normalized_stops:
            raise TrainNotFoundError(f"No valid stops parsed for train {train_no}")

        # Extract days of run
        days_of_run_raw = raw_data.get("DaysOfRun") or {}
        days_of_run: Dict[str, bool] = {
            day: bool(days_of_run_raw.get(day, False))
            for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        }

        # Extract classes
        classes_raw = raw_data.get("Classes") or []
        classes = [str(c).strip().upper() for c in classes_raw if c]

        # Extract total stats
        tot_duration = int(raw_data.get("TotalDuration", 0) or 0)
        tot_distance = parse_distance_km(raw_data.get("TotalDistance", 0))
        tot_stops_raw = raw_data.get("TotalNumberOfStops")
        tot_stops = int(tot_stops_raw) if tot_stops_raw and str(tot_stops_raw).isdigit() else len(normalized_stops)

        return {
            "train_no": str(raw_data.get("TrainNumberString") or raw_data.get("TrainNo") or train_no),
            "train_name": str(raw_data.get("TrainName", "")).strip(),
            "train_type": str(raw_data.get("TrainType", "Express")).strip(),
            "source_station_name": str(raw_data.get("Source", normalized_stops[0]["station_name"])).strip(),
            "source_station_code": str(raw_data.get("SourceCode", normalized_stops[0]["station_code"])).strip().upper(),
            "destination_station_name": str(raw_data.get("Destination", normalized_stops[-1]["station_name"])).strip(),
            "destination_station_code": str(raw_data.get("DestinationCode", normalized_stops[-1]["station_code"])).strip().upper(),
            "days_of_run": days_of_run,
            "classes": classes,
            "total_duration_minutes": tot_duration,
            "total_distance_km": tot_distance or normalized_stops[-1]["distance_from_origin_km"],
            "total_stops": tot_stops,
            "schedule": normalized_stops,
        }

    async def fetch_schedule(self, train_no: str) -> Dict[str, Any]:
        """
        Asynchronously fetches and normalizes train schedule from upstream with retries and circuit breaker.
        """
        self.circuit_breaker.before_call()

        headers = config.get_schedule_headers(train_no)
        cookies = config.get_schedule_cookies()
        params = {"trainNo": train_no}

        attempts = config.MAX_RETRIES + 1
        last_exc: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                response = await self._client.get(
                    self.url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                )

                # Check if RedBus returned 500 with train-not-found error payload
                if response.status_code == 500:
                    try:
                        err_payload = response.json()
                        if (
                            err_payload.get("data", {}).get("status") == 417
                            or err_payload.get("data", {}).get("data", {}).get("errorcode") == "114"
                        ):
                            raise TrainNotFoundError(f"Train {train_no} not found or schedule unavailable")
                    except (ValueError, KeyError):
                        pass

                response.raise_for_status()
                raw_json = response.json()
                parsed = self._parse_upstream_payload(raw_json, train_no)
                self.circuit_breaker.record_success()
                return parsed

            except TrainNotFoundError:
                # Do not record TrainNotFoundError as an upstream circuit-breaker failure
                raise

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    f"RedBus schedule timeout for train {train_no} "
                    f"(attempt {attempt + 1}/{attempts}): {exc}"
                )
                if attempt < attempts - 1:
                    jitter = random.uniform(0.05, 0.2)
                    await asyncio.sleep((config.BACKOFF_FACTOR * (2 ** attempt)) + jitter)

            except httpx.ConnectError as exc:
                last_exc = exc
                logger.warning(
                    f"RedBus connection error for train {train_no} "
                    f"(attempt {attempt + 1}/{attempts}): {exc}"
                )
                if attempt < attempts - 1:
                    jitter = random.uniform(0.05, 0.2)
                    await asyncio.sleep((config.BACKOFF_FACTOR * (2 ** attempt)) + jitter)

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else 0
                if status == 404:
                    raise TrainNotFoundError(f"Train {train_no} not found") from exc
                logger.warning(
                    f"RedBus HTTP {status} error for train {train_no} "
                    f"(attempt {attempt + 1}/{attempts}): {exc}"
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(config.BACKOFF_FACTOR * (2 ** attempt))

            except Exception as exc:
                last_exc = exc
                logger.error(f"Unexpected error fetching schedule for train {train_no}: {exc}")
                break

        # Record failure on circuit breaker after retries exhausted
        self.circuit_breaker.record_failure(last_exc)

        if isinstance(last_exc, httpx.TimeoutException):
            raise UpstreamTimeoutError(f"Upstream schedule provider timed out for train {train_no}") from last_exc
        if isinstance(last_exc, httpx.ConnectError):
            raise UpstreamConnectionError(f"Failed to connect to schedule provider for train {train_no}") from last_exc
        raise UpstreamServiceError(f"Schedule provider error for train {train_no}: {last_exc}") from last_exc

    async def aclose(self) -> None:
        """Close underlying async HTTP client pool."""
        if not self._client.is_closed:
            await self._client.aclose()
