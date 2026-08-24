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
from typing import Optional

from app.interfaces.hotel import HotelProvider
from app.interfaces.route import RouteProvider
from app.interfaces.tourism import TourismProvider
from app.interfaces.transport import BusProvider, TrainProvider

from app.business.preferences import (
    resolve_hotel_params,
    resolve_route_params,
    resolve_tourism_params,
    resolve_transport_params,
)
from app.schemas.context import ServiceStatus, TripContext
from app.schemas.request import TripRequest

logger = logging.getLogger(__name__)


class TripOrchestrator:
    """
    Coordinates concurrent data collection from all registered providers.
    Uses granular in-memory TTL caching so changing one parameter (e.g. date)
    doesn't invalidate cache for independent domains (e.g. attractions, route).
    """

    def __init__(
        self,
        tourism:  TourismProvider,
        hotels:   HotelProvider,
        buses:    BusProvider,
        trains:   TrainProvider,
        route:    RouteProvider,
    ):
        self._tourism = tourism
        self._hotels  = hotels
        self._buses   = buses
        self._trains  = trains
        self._route   = route
        
        # Granular TTL Caches
        self._cache_ttl = 900  # 15 minutes
        self._cache_tourism = {}
        self._cache_route = {}
        self._cache_hotels = {}
        self._cache_buses = {}
        self._cache_trains = {}

    # ── Granular Cache Wrappers ───────────────────────────────────────────────

    async def _get_tourism(self, city: str, limit: int):
        key = f"{city}:{limit}"
        now = time.time()
        if key in self._cache_tourism and now < self._cache_tourism[key][0]:
            logger.info("Cache HIT: Tourism")
            return self._cache_tourism[key][1]
        
        data = await self._tourism.get_attractions(city, limit)
        self._cache_tourism[key] = (now + self._cache_ttl, data)
        return data

    async def _get_route(self, origin: str, destination: str):
        key = f"{origin}:{destination}"
        now = time.time()
        if key in self._cache_route and now < self._cache_route[key][0]:
            logger.info("Cache HIT: Route")
            return self._cache_route[key][1]
            
        data = await self._route.get_route(origin, destination)
        self._cache_route[key] = (now + self._cache_ttl, data)
        return data

    async def _get_hotels(self, city: str, check_in: str, check_out: str, adults: int, children: int):
        key = f"{city}:{check_in}:{check_out}:{adults}:{children}"
        now = time.time()
        if key in self._cache_hotels and now < self._cache_hotels[key][0]:
            logger.info("Cache HIT: Hotels")
            return self._cache_hotels[key][1]
            
        data = await self._hotels.get_hotels(city, check_in, check_out, adults, children)
        self._cache_hotels[key] = (now + self._cache_ttl, data)
        return data

    async def _get_buses(self, source: str, destination: str, date: str):
        key = f"{source}:{destination}:{date}"
        now = time.time()
        if key in self._cache_buses and now < self._cache_buses[key][0]:
            logger.info("Cache HIT: Buses")
            return self._cache_buses[key][1]
            
        data = await self._buses.get_buses(source, destination, date)
        self._cache_buses[key] = (now + self._cache_ttl, data)
        return data

    async def _get_trains(self, source: str, destination: str, date: str):
        key = f"{source}:{destination}:{date}"
        now = time.time()
        if key in self._cache_trains and now < self._cache_trains[key][0]:
            logger.info("Cache HIT: Trains")
            return self._cache_trains[key][1]
            
        data = await self._trains.get_trains(source, destination, date)
        self._cache_trains[key] = (now + self._cache_ttl, data)
        return data

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
        route_p     = resolve_route_params(trip)

        # ── Concurrent collection ─────────────────────────────────────────
        (
            attractions,
            hotels,
            outbound_buses,
            return_buses,
            outbound_trains,
            return_trains,
            route,
        ) = await asyncio.gather(
            self._get_tourism(tourism_p.city, tourism_p.limit),
            self._get_hotels(hotel_p.city, hotel_p.check_in, hotel_p.check_out, hotel_p.adults, hotel_p.children),
            self._get_buses(transport_p.source, transport_p.destination, transport_p.outbound_date),
            self._get_buses(transport_p.destination, transport_p.source, transport_p.return_date),
            self._get_trains(transport_p.source, transport_p.destination, transport_p.outbound_date),
            self._get_trains(transport_p.destination, transport_p.source, transport_p.return_date),
            self._get_route(route_p.origin, route_p.destination),
        )

        # ── Service availability tracking ─────────────────────────────────
        status = ServiceStatus(
            tourism = bool(attractions),
            hotels  = bool(hotels),
            buses   = bool(outbound_buses or return_buses),
            trains  = bool(outbound_trains or return_trains),
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
            route=route,
            service_status=status,
        )
