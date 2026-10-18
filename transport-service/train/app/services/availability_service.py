"""
Train Availability Service

Facade for retrieving live train seat availability.
Implements:
  - In-flight request coalescing (Singleflight pattern)
  - Concurrency bounds via asyncio.Semaphore
  - Decoupled provider dependency injection
  - 100% backward compatibility for synchronous callers (TrainService._enrich_availability)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from app.config import config
from app.exceptions import (
    UpstreamTimeoutError,
    UpstreamConnectionError,
    UpstreamServiceError,
    CircuitBreakerOpenError,
)
from app.models.availability_models import AvailabilityRequest
from app.services.availability_provider import (
    AvailabilityProvider,
    ConfirmTktAvailabilityProvider,
    parse_booking_status,
)

logger = logging.getLogger(__name__)


class AvailabilityService:
    """
    Stateless, concurrency-safe availability service.
    """

    def __init__(
        self,
        provider: Optional[AvailabilityProvider] = None,
        max_concurrent: Optional[int] = None,
    ) -> None:
        self.provider: AvailabilityProvider = provider or ConfirmTktAvailabilityProvider()
        self.max_concurrent = max_concurrent or config.MAX_CONCURRENT_AVAILABILITY

        # Singleflight in-flight request coalescing map:
        # key -> asyncio.Future
        self._in_flight: Dict[Tuple[str, str, str, str, str, str], asyncio.Future] = {}
        self._in_flight_lock = asyncio.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None

        # In-memory TTL snapshot cache: key -> (timestamp, result_dict)
        self._cache: Dict[Tuple[str, str, str, str, str, str], Tuple[float, Dict[str, Any]]] = {}
        self.cache_ttl: int = config.AVAILABILITY_CACHE_TTL

        # Backward compatibility properties
        self.url = config.AVAILABILITY_API
        self.headers = config.TRAIN_HEADERS

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    @staticmethod
    def _parse_booking_status(availability_str: str) -> str:
        """Standardizes booking status strings. Backward compatibility helper."""
        return parse_booking_status(availability_str)

    async def async_fetch_availability(
        self,
        request: AvailabilityRequest,
    ) -> Dict[str, Any]:
        """
        Asynchronously fetches live availability with in-memory TTL cache,
        in-flight request coalescing, and bounded concurrency.
        """
        import time

        key = (
            request.train_no,
            request.source,
            request.destination,
            request.travel_class,
            request.date,
            request.quota,
        )

        # 1. Check in-memory snapshot cache
        if self.cache_ttl > 0 and key in self._cache:
            cached_at, cached_result = self._cache[key]
            if time.monotonic() - cached_at < self.cache_ttl:
                return cached_result

        loop = asyncio.get_running_loop()

        # 2. Check if an identical request is already in-flight (Singleflight)
        async with self._in_flight_lock:
            if key in self._in_flight:
                logger.info(f"[Singleflight] Coalescing duplicate in-flight availability request for {key}")
                existing_future = self._in_flight[key]
                return await asyncio.shield(existing_future)

            # Create a new future for subsequent callers to await
            future: asyncio.Future = loop.create_future()
            self._in_flight[key] = future

        # 3. Execute upstream request under bounded semaphore
        semaphore = self._get_semaphore()
        async with semaphore:
            try:
                result = await self.provider.fetch_availability(
                    train_no=request.train_no,
                    source=request.source,
                    destination=request.destination,
                    travel_class=request.travel_class,
                    date=request.date,
                    quota=request.quota,
                )
                if not future.done():
                    future.set_result(result)

                # Store in TTL snapshot cache on success
                if self.cache_ttl > 0 and result.get("success"):
                    if len(self._cache) > 2000:
                        self._cache.clear()
                    self._cache[key] = (time.monotonic(), result)

                return result
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
                raise exc
            finally:
                async with self._in_flight_lock:
                    self._in_flight.pop(key, None)

    def fetch_availability(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """
        Synchronous availability fetch method.
        Preserves 100% backward compatibility for TrainService._enrich_availability
        and existing unit tests.
        """
        try:
            return self.provider.fetch_availability_sync(
                train_no=train_no,
                source=source,
                destination=destination,
                travel_class=travel_class,
                date=date,
                quota=quota,
            )
        except Exception as e:
            logger.warning(f"Live availability sync fetch failed for {train_no} {travel_class}: {e}")
            return {
                "success": False,
                "message": str(e),
                "data": None,
            }

    async def aclose(self) -> None:
        """Release provider resources."""
        if hasattr(self.provider, "aclose"):
            await self.provider.aclose()


# Default service instance for dependency injection
_default_availability_service: Optional[AvailabilityService] = None


def get_availability_service() -> AvailabilityService:
    """Dependency injection factory for FastAPI routes."""
    global _default_availability_service
    if _default_availability_service is None:
        _default_availability_service = AvailabilityService()
    return _default_availability_service
