"""
Availability Provider Protocol & ConfirmTkt / Ixigo Implementation

Provides decoupled, resilient, non-blocking upstream access to live train availability.
Features:
  - Connection pooling with httpx.AsyncClient
  - Bounded exponential backoff with jitter on transient failures
  - Circuit Breaker integration
  - Defensive response parsing
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import httpx

from app.config import config
from app.exceptions import (
    UpstreamTimeoutError,
    UpstreamConnectionError,
    UpstreamServiceError,
    CircuitBreakerOpenError,
)
from app.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


def parse_booking_status(availability_str: str) -> str:
    """Parses raw availability string into standardized booking_status."""
    av_upper = str(availability_str).strip().upper()
    if "REGRET" in av_upper:
        return "REGRET"
    if "CURR_AVBL" in av_upper or "AVAILABLE" in av_upper or "AVL" in av_upper:
        return "AVAILABLE"
    if "RAC" in av_upper:
        return "RAC"
    if "WL" in av_upper or "WAITLIST" in av_upper:
        return "WL"
    return "UNKNOWN"


@runtime_checkable
class AvailabilityProvider(Protocol):
    """Abstract interface for train availability data providers."""

    async def fetch_availability(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """Fetch live availability asynchronously."""
        ...

    def fetch_availability_sync(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """Fetch live availability synchronously (for backward compatibility)."""
        ...

    async def aclose(self) -> None:
        """Release underlying HTTP client resources."""
        ...


class ConfirmTktAvailabilityProvider:
    """
    Production-grade ConfirmTkt / Ixigo live availability provider.
    Uses non-blocking httpx.AsyncClient with circuit breaker and retry bounds.
    """

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self.url = config.AVAILABILITY_API
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            reset_timeout=config.CIRCUIT_BREAKER_RESET_TIMEOUT,
            name="confirmtkt-availability",
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
        self._client = client or httpx.AsyncClient(timeout=timeout, limits=limits)
        self._sync_client: Optional[httpx.Client] = None

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None or self._sync_client.is_closed:
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
            self._sync_client = httpx.Client(timeout=timeout, limits=limits)
        return self._sync_client

    def _build_params(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        quota: str,
        date: str,
    ) -> Dict[str, str]:
        return {
            "trainNo": train_no,
            "sourceStationCode": source,
            "destinationStationCode": destination,
            "travelClass": travel_class,
            "quota": quota,
            "dateOfJourney": date,
        }

    def _parse_upstream_payload(
        self,
        raw_data: Dict[str, Any],
        train_no: str,
        travel_class: str,
        quota: str,
    ) -> Dict[str, Any]:
        """Defensively parse raw ConfirmTkt JSON response."""
        data = raw_data.get("data", raw_data)
        if not isinstance(data, dict):
            data = {}

        avl_day_list = data.get("avlDayList", [])
        avl_info = avl_day_list[0] if avl_day_list and isinstance(avl_day_list, list) else {}
        if not isinstance(avl_info, dict):
            avl_info = {}

        availability_str = str(
            avl_info.get("availabilityDisplayName") or avl_info.get("availablityStatus") or ""
        ).strip()
        booking_status = parse_booking_status(availability_str)

        # Extract fares
        fare_info = data.get("fareInfo", {})
        if not isinstance(fare_info, dict):
            fare_info = {}

        fare_val = fare_info.get("baseFare", fare_info.get("totalFare", 0))
        try:
            fare = int(float(fare_val))
        except (ValueError, TypeError):
            fare = 0

        total_fare_val = fare_info.get("totalCollectibleAmount", fare_info.get("totalFare", fare))
        try:
            total_fare = int(float(total_fare_val))
        except (ValueError, TypeError):
            total_fare = fare

        # Prediction
        prediction_val = avl_info.get("predictionPercentage", 0)
        try:
            prediction = int(prediction_val)
        except (ValueError, TypeError):
            prediction = 0

        booking_enabled = bool(avl_info.get("enableBookButton", True))
        if "REGRET" in availability_str.upper():
            booking_enabled = False

        last_updated = str(data.get("timeStamp", datetime.datetime.now().isoformat()))

        # Next available dates
        next_available_dates: List[str] = []
        if isinstance(avl_day_list, list) and len(avl_day_list) > 1:
            for item in avl_day_list[1:]:
                if isinstance(item, dict) and item.get("availablityDate"):
                    next_available_dates.append(str(item.get("availablityDate")))

        return {
            "success": True,
            "message": "Live availability fetched",
            "data": {
                "train_number": train_no,
                "travel_class": travel_class,
                "quota": quota,
                "availability": availability_str,
                "booking_status": booking_status,
                "prediction": prediction,
                "fare": fare,
                "total_fare": total_fare,
                "booking_enabled": booking_enabled,
                "last_updated": last_updated,
                "next_available_dates": next_available_dates,
            },
        }

    async def fetch_availability(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """
        Asynchronously fetches live availability with circuit breaker and bounded backoff.
        """
        self.circuit_breaker.before_call()

        params = self._build_params(train_no, source, destination, travel_class, quota, date)
        headers = config.get_train_headers()

        last_exc: Optional[Exception] = None
        max_attempts = 1 + config.MAX_RETRIES

        for attempt in range(max_attempts):
            try:
                logger.info(
                    f"ConfirmTkt API Request (attempt {attempt+1}/{max_attempts}): "
                    f"POST {self.url} with train={train_no}, route={source}->{destination}, class={travel_class}"
                )
                response = await self._client.post(
                    self.url,
                    params=params,
                    headers=headers,
                )

                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    raw_data = response.json()
                    return self._parse_upstream_payload(raw_data, train_no, travel_class, quota)

                # Handle transient 5xx or 429
                if response.status_code in (429, 502, 503, 504):
                    logger.warning(
                        f"ConfirmTkt API transient error: HTTP {response.status_code} on attempt {attempt+1}"
                    )
                    last_exc = UpstreamServiceError(f"Upstream returned HTTP {response.status_code}")
                elif response.status_code == 404:
                    # Train or route not found
                    return {
                        "success": False,
                        "message": f"Train {train_no} not found or no schedule between {source} and {destination}",
                        "data": None,
                    }
                else:
                    logger.warning(f"ConfirmTkt API non-retryable status: HTTP {response.status_code}")
                    last_exc = UpstreamServiceError(f"Upstream returned HTTP {response.status_code}")
                    break  # Non-retryable HTTP error

            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                logger.warning(f"ConfirmTkt API timeout on attempt {attempt+1}: {exc}")
                last_exc = UpstreamTimeoutError("ConfirmTkt API request timed out")
                break
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                logger.warning(f"ConfirmTkt API connection error on attempt {attempt+1}: {exc}")
                last_exc = UpstreamConnectionError("Unable to connect to ConfirmTkt API")
            except Exception as exc:
                logger.error(f"Unexpected error calling ConfirmTkt API: {exc}")
                last_exc = exc
                break

            # Exponential backoff with jitter before next attempt
            if attempt < max_attempts - 1:
                backoff = min(1.5, config.BACKOFF_FACTOR * (2 ** attempt) + random.uniform(0.05, 0.15))
                await asyncio.sleep(backoff)

        # All attempts exhausted
        self.circuit_breaker.record_failure(last_exc)
        if isinstance(last_exc, (UpstreamTimeoutError, UpstreamConnectionError, UpstreamServiceError)):
            raise last_exc
        raise UpstreamServiceError(f"ConfirmTkt API request failed: {last_exc}")

    def fetch_availability_sync(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """
        Synchronous fallback for existing callers (e.g. TrainService._enrich_availability).
        """
        self.circuit_breaker.before_call()
        params = self._build_params(train_no, source, destination, travel_class, quota, date)
        headers = config.get_train_headers()
        client = self._get_sync_client()

        last_exc: Optional[Exception] = None
        max_attempts = 1 + config.MAX_RETRIES

        for attempt in range(max_attempts):
            try:
                response = client.post(self.url, params=params, headers=headers)
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    raw_data = response.json()
                    return self._parse_upstream_payload(raw_data, train_no, travel_class, quota)

                if response.status_code in (429, 502, 503, 504):
                    last_exc = UpstreamServiceError(f"Upstream returned HTTP {response.status_code}")
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": f"Train {train_no} not found or no schedule between {source} and {destination}",
                        "data": None,
                    }
                else:
                    last_exc = UpstreamServiceError(f"Upstream returned HTTP {response.status_code}")
                    break
            except httpx.TimeoutException as exc:
                last_exc = UpstreamTimeoutError("ConfirmTkt API request timed out")
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_exc = UpstreamConnectionError("Unable to connect to ConfirmTkt API")
            except Exception as exc:
                last_exc = exc
                break

            if attempt < max_attempts - 1:
                time_sleep = min(1.0, config.BACKOFF_FACTOR * (2 ** attempt))
                import time
                time.sleep(time_sleep)

        self.circuit_breaker.record_failure(last_exc)
        return {
            "success": False,
            "message": str(last_exc) if last_exc else "Failed to fetch availability",
            "data": None,
        }

    async def aclose(self) -> None:
        """Close underlying clients cleanly."""
        if not self._client.is_closed:
            await self._client.aclose()
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()
