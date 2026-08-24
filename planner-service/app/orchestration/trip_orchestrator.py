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

    Constructor injection makes this unit-testable — pass mock providers
    in tests without touching the HTTP layer.

    To add a new provider (e.g. RestaurantProvider):
      1. Add it as a constructor argument with a default of None.
      2. Add a gather call in _collect().
      3. Populate the new field on TripContext.
      → Zero changes to existing gather calls or schema contracts.
    """

    def __init__(
        self,
        tourism:  TourismProvider,
        hotels:   HotelProvider,
        buses:    BusProvider,
        trains:   TrainProvider,
        route:    RouteProvider,
        # Future: restaurants: Optional[RestaurantProvider] = None,
        # Future: flights:     Optional[FlightProvider]     = None,
    ):
        self._tourism = tourism
        self._hotels  = hotels
        self._buses   = buses
        self._trains  = trains
        self._route   = route

    async def build_context(self, trip: TripRequest) -> TripContext:
        """
        Resolve parameters, gather all service data concurrently,
        and assemble a TripContext.
        """
        # ── Resolve parameters via business layer ─────────────────────────
        tourism_p   = resolve_tourism_params(trip)
        hotel_p     = resolve_hotel_params(trip)
        transport_p = resolve_transport_params(trip)
        route_p     = resolve_route_params(trip)

        # ── Concurrent collection ─────────────────────────────────────────
        # Every call is wrapped so a provider failure returns an empty result
        # rather than propagating an exception.
        (
            attractions,
            hotels,
            outbound_buses,
            return_buses,
            outbound_trains,
            return_trains,
            route,
        ) = await asyncio.gather(
            self._tourism.get_attractions(
                city=tourism_p.city,
                limit=tourism_p.limit,
            ),
            self._hotels.get_hotels(
                city=hotel_p.city,
                check_in=hotel_p.check_in,
                check_out=hotel_p.check_out,
                adults=hotel_p.adults,
                children=hotel_p.children,
            ),
            self._buses.get_buses(
                source=transport_p.source,
                destination=transport_p.destination,
                journey_date=transport_p.outbound_date,
            ),
            self._buses.get_buses(
                source=transport_p.destination,
                destination=transport_p.source,
                journey_date=transport_p.return_date,
            ),
            self._trains.get_trains(
                source=transport_p.source,
                destination=transport_p.destination,
                journey_date=transport_p.outbound_date,
            ),
            self._trains.get_trains(
                source=transport_p.destination,
                destination=transport_p.source,
                journey_date=transport_p.return_date,
            ),
            self._route.get_route(
                origin=route_p.origin,
                destination=route_p.destination,
            ),
        )

        # ── Service availability tracking ─────────────────────────────────
        status = ServiceStatus(
            tourism = bool(attractions),
            hotels  = bool(hotels),
            buses   = bool(outbound_buses or return_buses),
            trains  = bool(outbound_trains or return_trains),
            route   = route is not None,
        )

        logger.info(
            "TripOrchestrator complete | "
            "attractions=%d hotels=%d outbound_buses=%d return_buses=%d "
            "outbound_trains=%d return_trains=%d route=%s",
            len(attractions), len(hotels),
            len(outbound_buses), len(return_buses),
            len(outbound_trains), len(return_trains),
            "ok" if route else "unavailable",
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
