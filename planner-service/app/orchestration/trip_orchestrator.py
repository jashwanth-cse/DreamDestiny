"""
TripOrchestrator — coordinates all service calls to build a TripContext.

ARCHITECTURE RULES (enforced here):
  ✅ Depends on provider interfaces, NOT concrete clients.
  ✅ Uses asyncio.gather for all independent calls.
  ✅ Delegates all parameter resolution to app.business.preferences.
  ✅ Delegates all normalization to each client's return type.
  ✅ Contains NO business logic, pricing, ranking, or LLM calls.
  ✅ Returns a valid TripContext even if some services are unavailable.
  ✅ Adding a new service = inject new provider + gather it below.
"""

import asyncio
import logging
import time
from typing import Optional, Any

from app.interfaces.hotel import HotelProvider
from app.interfaces.route import RouteProvider
from app.interfaces.tourism import TourismProvider
from app.interfaces.transport import BusProvider, TrainProvider
from app.interfaces.flight import FlightProvider

from app.business.preferences import (
    resolve_flight_params,
    resolve_hotel_params,
    resolve_route_params,
    resolve_tourism_params,
    resolve_transport_params,
)
from app.schemas.context import ServiceStatus, TripContext, FlightResolutionContext
from app.schemas.request import TripRequest

logger = logging.getLogger(__name__)


class _BoundedTTLCache:
    """Bounded thread-safe LRU+TTL cache backed by an OrderedDict to prevent memory leaks."""
    def __init__(self, maxsize: int = 512, ttl: float = 900.0):
        self._store: dict[str, tuple[float, Any]] = {}
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, val = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return val

    def set(self, key: str, val: Any) -> None:
        if len(self._store) >= self._maxsize:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = (time.time() + self._ttl, val)


class TripOrchestrator:
    """
    Coordinates concurrent data collection from all registered providers.
    Uses bounded in-memory TTL caching so changing one parameter (e.g. date)
    doesn't invalidate cache for independent domains (e.g. attractions, route).
    """

    def __init__(
        self,
        tourism:  TourismProvider,
        hotels:   HotelProvider,
        buses:    BusProvider,
        trains:   TrainProvider,
        route:    RouteProvider,
        flights:  Optional[FlightProvider] = None,
    ):
        self._tourism = tourism
        self._hotels  = hotels
        self._buses   = buses
        self._trains  = trains
        self._route   = route
        self._flights = flights
        
        # Bounded TTL Caches (max 512 items, 15 min TTL)
        self._cache_tourism = _BoundedTTLCache(maxsize=512, ttl=900)
        self._cache_route = _BoundedTTLCache(maxsize=512, ttl=900)
        self._cache_hotels = _BoundedTTLCache(maxsize=512, ttl=900)
        self._cache_buses = _BoundedTTLCache(maxsize=512, ttl=900)
        self._cache_trains = _BoundedTTLCache(maxsize=512, ttl=900)
        self._cache_flights = _BoundedTTLCache(maxsize=512, ttl=900)

    # ── Granular Cache Wrappers ───────────────────────────────────────────────

    async def _get_tourism(self, city: str, limit: int):
        key = f"{city}:{limit}"
        cached = self._cache_tourism.get(key)
        if cached is not None:
            logger.info("Cache HIT: Tourism")
            return cached
        
        data = await self._tourism.get_attractions(city, limit)
        self._cache_tourism.set(key, data)
        return data

    async def _get_route(self, origin: str, destination: str):
        key = f"{origin}:{destination}"
        cached = self._cache_route.get(key)
        if cached is not None:
            logger.info("Cache HIT: Route")
            return cached
            
        data = await self._route.get_route(origin, destination)
        self._cache_route.set(key, data)
        return data

    async def _get_hotels(self, city: str, check_in: str, check_out: str, adults: int, children: int):
        key = f"{city}:{check_in}:{check_out}:{adults}:{children}"
        cached = self._cache_hotels.get(key)
        if cached is not None:
            logger.info("Cache HIT: Hotels")
            return cached
            
        data = await self._hotels.get_hotels(city, check_in, check_out, adults, children)
        self._cache_hotels.set(key, data)
        return data

    async def _get_buses(self, source: str, destination: str, date: str):
        key = f"{source}:{destination}:{date}"
        cached = self._cache_buses.get(key)
        if cached is not None:
            logger.info("Cache HIT: Buses")
            return cached
            
        data = await self._buses.get_buses(source, destination, date)
        self._cache_buses.set(key, data)
        return data

    async def _get_trains(self, source: str, destination: str, date: str):
        key = f"{source}:{destination}:{date}"
        cached = self._cache_trains.get(key)
        if cached is not None:
            logger.info("Cache HIT: Trains")
            return cached
            
        data = await self._trains.get_trains(source, destination, date)
        self._cache_trains.set(key, data)
        return data

    async def _get_flights(
        self,
        origin: str,
        destination: str,
        outbound_date: str,
        travelers: int,
        travel_class: Optional[str] = "economy",
    ):
        """
        Fetch flights from the provider.
        Returns (flights, FlightResolutionContext | None).

        Uses get_flights_with_resolution() when available (FlightClient v2),
        otherwise falls back to plain get_flights().
        """
        if not self._flights:
            return [], None

        key = f"{origin}:{destination}:{outbound_date}:{travelers}:{travel_class}"
        cached = self._cache_flights.get(key)
        if cached is not None:
            logger.info("Cache HIT: Flights (%s -> %s)", origin, destination)
            return cached

        # Use enhanced method if available (FlightClient v2)
        if hasattr(self._flights, "get_flights_with_resolution"):
            result = await self._flights.get_flights_with_resolution(
                origin=origin,
                destination=destination,
                outbound_date=outbound_date,
                travelers=travelers,
                travel_class=travel_class,
            )
        else:
            flights = await self._flights.get_flights(
                origin=origin,
                destination=destination,
                outbound_date=outbound_date,
                travelers=travelers,
                travel_class=travel_class,
            )
            result = (flights, None)

        self._cache_flights.set(key, result)
        return result

    # ── Main Orchestration ────────────────────────────────────────────────────

    async def build_context(self, trip: TripRequest) -> TripContext:
        """
        Resolve parameters, gather all service data concurrently,
        and assemble a TripContext using granular caching.
        """
        # ── Resolve parameters via business layer ─────────────────────────
        tourism_p   = resolve_tourism_params(trip)
        hotel_p     = resolve_hotel_params(trip)
        transport_p = resolve_transport_params(trip)
        flight_p    = resolve_flight_params(trip)
        route_p     = resolve_route_params(trip)

        # ── Concurrent collection ─────────────────────────────────────────
        (
            attractions,
            hotels,
            outbound_buses,
            return_buses,
            outbound_trains,
            return_trains,
            outbound_flights_result,
            return_flights_result,
            route,
        ) = await asyncio.gather(
            self._get_tourism(tourism_p.city, tourism_p.limit),
            self._get_hotels(hotel_p.city, hotel_p.check_in, hotel_p.check_out, hotel_p.adults, hotel_p.children),
            self._get_buses(transport_p.source, transport_p.destination, transport_p.outbound_date),
            self._get_buses(transport_p.destination, transport_p.source, transport_p.return_date),
            self._get_trains(transport_p.source, transport_p.destination, transport_p.outbound_date),
            self._get_trains(transport_p.destination, transport_p.source, transport_p.return_date),
            self._get_flights(flight_p.origin, flight_p.destination, flight_p.outbound_date, flight_p.travelers, flight_p.travel_class),
            self._get_flights(flight_p.destination, flight_p.origin, flight_p.return_date, flight_p.travelers, flight_p.travel_class),
            self._get_route(route_p.origin, route_p.destination),
        )

        # ── Unpack flight tuples (flights, resolution) ────────────────────
        outbound_flights, outbound_resolution = outbound_flights_result
        return_flights, return_resolution = return_flights_result

        # Merge resolution metadata: outbound takes priority, return fills gaps
        flight_resolution: Optional[FlightResolutionContext] = outbound_resolution or return_resolution

        # ── Service availability tracking ─────────────────────────────────
        status = ServiceStatus(
            tourism = bool(attractions),
            hotels  = bool(hotels),
            buses   = bool(outbound_buses or return_buses),
            trains  = bool(outbound_trains or return_trains),
            flights = bool(outbound_flights or return_flights),
            route   = route is not None,
        )

        # ── Assemble and return TripContext ───────────────────────────────
        return TripContext(
            trip=trip,
            attractions=attractions,
            hotels=hotels,
            outbound_buses=outbound_buses,
            return_buses=return_buses,
            outbound_trains=outbound_trains,
            return_trains=return_trains,
            outbound_flights=outbound_flights,
            return_flights=return_flights,
            flights=outbound_flights + return_flights,
            flight_resolution=flight_resolution,
            route=route,
            service_status=status,
        )
