"""
Unit tests for Flight Service integration into Planner Service:
1. _filter_flights deterministic filtering
2. ItineraryValidator grounding & CostBreakdown calculation
3. TripOrchestrator context assembly with FlightProvider
"""

import asyncio
from datetime import date
import pytest

from app.schemas.context import (
    TripContext,
    FlightContext,
    HotelContext,
    HotelPriceContext,
    ServiceStatus,
)
from app.schemas.request import (
    TripRequest,
    TripPreferences,
    BudgetPreferences,
    TransportPreferences,
    HotelPreferences,
    ActivityPreferences,
    TransportPref,
)
from app.schemas.itinerary import (
    Itinerary,
    ItinerarySummary,
    HotelDecision,
    TransportDecision,
    DayPlan,
    Activity,
)
from app.agents.planning_agent import _filter_flights
from app.business.itinerary_validator import ItineraryValidator
from app.interfaces.flight import FlightProvider
from app.orchestration.trip_orchestrator import TripOrchestrator


def _create_mock_trip_request(mode="flight") -> TripRequest:
    return TripRequest(
        origin="Chennai",
        destination="Coimbatore",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 18),
        travelers=2,
        preferences=TripPreferences(
            budget=BudgetPreferences(level="medium"),
            transport=TransportPreferences(mode=mode),
            hotel=HotelPreferences(category="mid_range"),
            activities=ActivityPreferences(pace="moderate", interests=["nature"]),
        ),
    )


def test_filter_flights():
    flights = [
        FlightContext(
            flight_id="FL-1",
            airline="IndiGo",
            flight_number="6E 101",
            departure_airport_code="MAA",
            arrival_airport_code="CJB",
            stops=1,
            price=4500.0,
            is_best_flight=False,
        ),
        FlightContext(
            flight_id="FL-2",
            airline="Air India",
            flight_number="AI 202",
            departure_airport_code="MAA",
            arrival_airport_code="CJB",
            stops=0,
            price=5200.0,
            is_best_flight=True,
        ),
        FlightContext(
            flight_id="FL-3",
            airline="SpiceJet",
            flight_number="SG 303",
            departure_airport_code="MAA",
            arrival_airport_code="CJB",
            stops=0,
            price=3800.0,
            is_best_flight=False,
        ),
    ]

    filtered = _filter_flights(flights, top_n=2)
    assert len(filtered) == 2
    # Best flight (is_best_flight=True) should be prioritized first
    assert filtered[0]["flight_id"] == "FL-2"
    # Second should be non-stop lowest price
    assert filtered[1]["flight_id"] == "FL-3"


def test_itinerary_validator_flight_grounding_and_costs():
    trip = _create_mock_trip_request()

    outbound_flight = FlightContext(
        flight_id="6E-MAA-CJB-101",
        airline="IndiGo",
        flight_number="6E 101",
        departure_airport_code="MAA",
        arrival_airport_code="CJB",
        departure_time="08:00",
        arrival_time="09:15",
        price=3500.0,
        currency="INR",
        travel_class="economy",
    )
    return_flight = FlightContext(
        flight_id="6E-CJB-MAA-102",
        airline="IndiGo",
        flight_number="6E 102",
        departure_airport_code="CJB",
        arrival_airport_code="MAA",
        departure_time="18:00",
        arrival_time="19:15",
        price=3200.0,
        currency="INR",
        travel_class="economy",
    )
    hotel = HotelContext(
        id="hotel_taj_123",
        name="Taj Vivanta Coimbatore",
        price=HotelPriceContext(per_night=4000.0, total=12000.0),
    )

    context = TripContext(
        trip=trip,
        hotels=[hotel],
        outbound_flights=[outbound_flight],
        return_flights=[return_flight],
        flights=[outbound_flight, return_flight],
        service_status=ServiceStatus(hotels=True, flights=True),
    )

    itinerary = Itinerary(
        summary=ItinerarySummary(
            origin="Chennai",
            destination="Coimbatore",
            start_date="2026-10-15",
            end_date="2026-10-18",
            days=3,
            travelers=2,
            pace="moderate",
            budget_level="medium",
        ),
        hotel=HotelDecision(
            hotel_id="hotel_taj_123",
            hotel_name="Taj Vivanta Coimbatore",
            price_total=0.0,
        ),
        outbound_transport=TransportDecision(
            mode="flight",
            leg="Chennai -> Coimbatore",
            flight_id="6E-MAA-CJB-101",
            airline="IndiGo",
            flight_number="6E 101",
            departure_time="08:00",
            arrival_time="09:15",
            fare_per_person=0,
        ),
        return_transport=TransportDecision(
            mode="flight",
            leg="Coimbatore -> Chennai",
            flight_id="6E-CJB-MAA-102",
            airline="IndiGo",
            flight_number="6E 102",
            departure_time="18:00",
            arrival_time="19:15",
            fare_per_person=0,
        ),
        days=[
            DayPlan(
                day=1,
                date="2026-10-15",
                activities=[
                    Activity(
                        attraction_name="Marudhamalai Temple",
                        start_time="10:30",
                        duration_minutes=90,
                        estimated_cost=100.0,
                    )
                ],
            )
        ],
    )

    validator = ItineraryValidator()
    validated = validator.validate_and_calculate_costs(itinerary, context)

    assert validated.cost_breakdown is not None
    # 2 travelers: (3500 + 3200) * 2 = 13,400 transport
    assert validated.cost_breakdown.transport_cost == 13400.0
    # Hotel total = 12,000
    assert validated.cost_breakdown.hotel_cost == 12000.0
    # Activities = 100
    assert validated.cost_breakdown.activities_estimated_cost == 100.0
    # Total = 13400 + 12000 + 100 = 25500
    assert validated.cost_breakdown.total_cost == 25500.0
    assert validated.total_cost == 25500.0


class DummyFlightProvider(FlightProvider):
    async def get_flights(self, origin, destination, outbound_date, return_date=None, travelers=1, travel_class="economy"):
        return [
            FlightContext(
                flight_id=f"TEST-{origin}-{destination}",
                airline="Air India",
                flight_number="AI 101",
                departure_airport_code=origin[:3].upper(),
                arrival_airport_code=destination[:3].upper(),
                price=5000.0,
            )
        ]


class DummyProvider:
    async def get_attractions(self, *args, **kwargs): return []
    async def get_hotels(self, *args, **kwargs): return []
    async def get_buses(self, *args, **kwargs): return []
    async def get_trains(self, *args, **kwargs): return []
    async def get_route(self, *args, **kwargs): return None


def test_trip_orchestrator_with_flights():
    async def _run():
        orchestrator = TripOrchestrator(
            tourism=DummyProvider(),
            hotels=DummyProvider(),
            buses=DummyProvider(),
            trains=DummyProvider(),
            route=DummyProvider(),
            flights=DummyFlightProvider(),
        )
        trip = _create_mock_trip_request(mode="flight")
        context = await orchestrator.build_context(trip)

        assert context.service_status.flights is True
        assert len(context.outbound_flights) == 1
        assert len(context.return_flights) == 1
        assert len(context.flights) == 2
        assert context.outbound_flights[0].flight_id == "TEST-Chennai-Coimbatore"
        assert context.return_flights[0].flight_id == "TEST-Coimbatore-Chennai"

    asyncio.run(_run())
