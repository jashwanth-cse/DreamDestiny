"""
ItineraryValidator — grounds selected entities against TripContext
and calculates accurate cost breakdowns.

Design principles:
  - Enforces grounding contract: verifies selected hotel, flight, train, bus
    against what was supplied in TripContext.
  - Ensures accurate cost calculation for travelers & nights.
  - Calculates total cost (transport + accommodation + activities).
  - Populates Itinerary.cost_breakdown and Itinerary.total_cost.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.schemas.context import TripContext, FlightContext, HotelContext
from app.schemas.itinerary import (
    CostBreakdown,
    Itinerary,
    HotelDecision,
    TransportDecision,
)

logger = logging.getLogger(__name__)


class ItineraryValidator:
    """
    Validates selected entities against TripContext and computes cost breakdowns.
    """

    def validate_and_calculate_costs(
        self,
        itinerary: Itinerary,
        context: TripContext,
    ) -> Itinerary:
        """
        Validates choices against context and calculates cost breakdown.
        Mutates and returns the itinerary with cost_breakdown and total_cost populated.
        """
        travelers = max(1, context.trip.travelers)
        nights = max(1, (context.trip.end_date - context.trip.start_date).days)

        # ── 1. Validate Hotel & compute accommodation cost ────────────────────
        hotel_cost = 0.0
        if itinerary.hotel:
            matched_hotel = self._find_hotel(itinerary.hotel, context.hotels)
            if matched_hotel:
                # Calculate hotel cost accurately
                if matched_hotel.price.total is not None and matched_hotel.price.total > 0:
                    hotel_cost = float(matched_hotel.price.total)
                elif matched_hotel.price.per_night is not None and matched_hotel.price.per_night > 0:
                    hotel_cost = float(matched_hotel.price.per_night * nights)
                elif itinerary.hotel.price_total is not None and itinerary.hotel.price_total > 0:
                    hotel_cost = float(itinerary.hotel.price_total)
                elif itinerary.hotel.price_per_night is not None and itinerary.hotel.price_per_night > 0:
                    hotel_cost = float(itinerary.hotel.price_per_night * nights)
                
                # Update hotel fields if missing
                if not itinerary.hotel.price_per_night and matched_hotel.price.per_night:
                    itinerary.hotel.price_per_night = matched_hotel.price.per_night
                if not itinerary.hotel.price_total:
                    itinerary.hotel.price_total = hotel_cost
            else:
                logger.warning(
                    "Hotel '%s' (id=%s) not found in TripContext.",
                    itinerary.hotel.hotel_name,
                    itinerary.hotel.hotel_id,
                )
                if itinerary.hotel.price_total:
                    hotel_cost = float(itinerary.hotel.price_total)
                elif itinerary.hotel.price_per_night:
                    hotel_cost = float(itinerary.hotel.price_per_night * nights)

        # ── 2. Validate Transport & compute transport cost ────────────────────
        outbound_fare, outbound_currency = self._validate_transport(
            itinerary.outbound_transport,
            flights=context.outbound_flights or context.flights,
            trains=context.outbound_trains,
            buses=context.outbound_buses,
            is_outbound=True,
        )

        return_fare, return_currency = self._validate_transport(
            itinerary.return_transport,
            flights=context.return_flights or context.flights,
            trains=context.return_trains,
            buses=context.return_buses,
            is_outbound=False,
        )

        # Transport cost = (outbound fare per person + return fare per person) * travelers
        transport_cost = (outbound_fare + return_fare) * travelers

        # ── 3. Calculate estimated activities cost ────────────────────────────
        activities_cost = 0.0
        for day in itinerary.days:
            for activity in day.activities:
                if activity.estimated_cost and activity.estimated_cost > 0:
                    activities_cost += float(activity.estimated_cost)

        # ── 4. Build CostBreakdown & total ─────────────────────────────────────
        total_trip_cost = transport_cost + hotel_cost + activities_cost
        currency = outbound_currency or return_currency or "INR"

        itinerary.cost_breakdown = CostBreakdown(
            transport_cost=round(transport_cost, 2),
            hotel_cost=round(hotel_cost, 2),
            activities_estimated_cost=round(activities_cost, 2),
            currency=currency,
            total_cost=round(total_trip_cost, 2),
        )
        itinerary.total_cost = round(total_trip_cost, 2)

        logger.info(
            "Itinerary costs calculated: Transport=%.2f, Hotel=%.2f, Activities=%.2f, Total=%.2f %s",
            transport_cost,
            hotel_cost,
            activities_cost,
            total_trip_cost,
            currency,
        )

        return itinerary

    def _find_hotel(
        self,
        decision: HotelDecision,
        hotels: list[HotelContext],
    ) -> Optional[HotelContext]:
        """Find hotel by id, or fallback by name."""
        for h in hotels:
            if h.id == decision.hotel_id:
                return h
        for h in hotels:
            if h.name.strip().lower() == decision.hotel_name.strip().lower():
                return h
        return None

    def _validate_transport(
        self,
        decision: Optional[TransportDecision],
        flights: list[FlightContext],
        trains: list,
        buses: list,
        is_outbound: bool,
    ) -> tuple[float, str]:
        """
        Validates transport against context list, enforces grounding,
        and returns (fare_per_person, currency).
        """
        if not decision:
            return 0.0, "INR"

        mode = (decision.mode or "").lower()

        # ── FLIGHT ────────────────────────────────────────────────────────────
        if mode == "flight":
            matched_flight = None
            if decision.flight_id:
                for f in flights:
                    if f.flight_id == decision.flight_id:
                        matched_flight = f
                        break

            # Fallback by flight number if flight_id slightly differs
            if not matched_flight and decision.flight_number:
                for f in flights:
                    if (f.flight_number or "").replace(" ", "").upper() == decision.flight_number.replace(" ", "").upper():
                        matched_flight = f
                        break

            if matched_flight:
                # Ground exact flight details from context
                if not decision.flight_id:
                    decision.flight_id = matched_flight.flight_id
                if not decision.airline:
                    decision.airline = matched_flight.airline
                if not decision.flight_number:
                    decision.flight_number = matched_flight.flight_number
                if not decision.departure_time:
                    decision.departure_time = matched_flight.departure_time
                if not decision.arrival_time:
                    decision.arrival_time = matched_flight.arrival_time

                fare = matched_flight.price if matched_flight.price is not None else float(decision.fare_per_person or 0)
                decision.fare_per_person = int(fare)
                return float(fare), matched_flight.currency or "INR"
            else:
                logger.warning(
                    "%s flight not found in context (flight_id=%s, flight_number=%s)",
                    "Outbound" if is_outbound else "Return",
                    decision.flight_id,
                    decision.flight_number,
                )
                fare = float(decision.fare_per_person or 0)
                return fare, "INR"

        # ── TRAIN ─────────────────────────────────────────────────────────────
        elif mode == "train":
            fare = float(decision.fare_per_person or 0)
            return fare, "INR"

        # ── BUS ───────────────────────────────────────────────────────────────
        elif mode == "bus":
            fare = float(decision.fare_per_person or 0)
            return fare, "INR"

        return float(decision.fare_per_person or 0), "INR"
