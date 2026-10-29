"""
Train Schedule Service

High-performance, concurrency-safe facade for retrieving normalized train schedules.
Implements:
  - Strict input sanitization against train number regex (^[0-9]{4,5}$)
  - In-flight request coalescing (Singleflight pattern to eliminate thundering herds)
  - In-memory TTL snapshot cache (default 24h TTL for static timetables)
  - Bounded concurrency via asyncio.Semaphore
  - Decoupled provider dependency injection
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, Optional, Tuple

from app.config import config
from app.exceptions import InvalidRequestError
from app.models.schedule_models import TrainScheduleData
from app.services.schedule_provider import RedBusScheduleProvider, ScheduleProvider

logger = logging.getLogger(__name__)

# Strict regex matching 4 or 5 digit Indian Railways train numbers
TRAIN_NO_REGEX = re.compile(r"^[0-9]{4,5}$")


class ScheduleService:
    """
    Stateless, concurrency-safe train schedule service with multi-tier caching and Singleflight coalescing.
    """

    def __init__(
        self,
        provider: Optional[ScheduleProvider] = None,
        max_concurrent: Optional[int] = None,
        cache_ttl: Optional[int] = None,
    ) -> None:
        self.provider: ScheduleProvider = provider or RedBusScheduleProvider()
        self.max_concurrent = max_concurrent or config.MAX_CONCURRENT_SCHEDULE
        self.cache_ttl = cache_ttl if cache_ttl is not None else config.SCHEDULE_CACHE_TTL

        # Singleflight in-flight request coalescing map: train_no -> asyncio.Future
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._in_flight_lock = asyncio.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None

        # In-memory TTL snapshot cache: train_no -> (cached_at_monotonic, TrainScheduleData)
        self._cache: Dict[str, Tuple[float, TrainScheduleData]] = {}

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    @staticmethod
    def validate_train_number(train_no: str) -> str:
        """Sanitizes and validates 4 or 5 digit train number format."""
        if not train_no or not isinstance(train_no, str):
            raise InvalidRequestError("Train number must be a valid 4 or 5 digit string")
        clean_no = train_no.strip()
        if not TRAIN_NO_REGEX.match(clean_no):
            raise InvalidRequestError(
                f"Invalid train number format '{train_no}'. Must be 4 or 5 numeric digits."
            )
        return clean_no

    async def get_schedule(self, train_no: str) -> TrainScheduleData:
        """
        Asynchronously retrieves normalized train schedule with Singleflight coalescing and in-memory TTL cache.
        """
        clean_train_no = self.validate_train_number(train_no)

        # 1. Check in-memory snapshot cache (sub-millisecond fast path)
        if self.cache_ttl > 0 and clean_train_no in self._cache:
            cached_at, cached_data = self._cache[clean_train_no]
            if time.monotonic() - cached_at < self.cache_ttl:
                logger.debug(f"[ScheduleService] Cache hit for train {clean_train_no}")
                return cached_data

        loop = asyncio.get_running_loop()

        # 2. Check if an identical request is already in-flight (Singleflight coalescing)
        async with self._in_flight_lock:
            if clean_train_no in self._in_flight:
                logger.info(f"[Singleflight] Coalescing duplicate in-flight schedule request for train {clean_train_no}")
                existing_future = self._in_flight[clean_train_no]
                return await asyncio.shield(existing_future)

            future: asyncio.Future = loop.create_future()
            self._in_flight[clean_train_no] = future

        # 3. Execute upstream request under bounded concurrency semaphore
        semaphore = self._get_semaphore()
        async with semaphore:
            try:
                raw_result = await self.provider.fetch_schedule(clean_train_no)
                schedule_data = TrainScheduleData(**raw_result)

                if not future.done():
                    future.set_result(schedule_data)

                # Store in TTL cache on success
                if self.cache_ttl > 0:
                    # Guard memory usage against unbounded growth
                    if len(self._cache) > 4000:
                        self._cache.clear()
                    self._cache[clean_train_no] = (time.monotonic(), schedule_data)

                return schedule_data
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
                    # Mark exception as retrieved to prevent unhandled future warning when caller directly re-raises
                    try:
                        future.exception()
                    except BaseException:
                        pass
                raise exc
            finally:
                async with self._in_flight_lock:
                    self._in_flight.pop(clean_train_no, None)

    def clear_cache(self) -> None:
        """Invalidates all cached schedules."""
        self._cache.clear()

    async def aclose(self) -> None:
        """Releases underlying provider resources."""
        if hasattr(self.provider, "aclose"):
            await self.provider.aclose()


# Default singleton instance for dependency injection
_default_schedule_service: Optional[ScheduleService] = None


def get_schedule_service() -> ScheduleService:
    """Dependency injection factory for FastAPI routes."""
    global _default_schedule_service
    if _default_schedule_service is None:
        _default_schedule_service = ScheduleService()
    return _default_schedule_service
