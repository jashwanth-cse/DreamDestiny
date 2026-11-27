import asyncio
import importlib
from datetime import date

from app.business.itinerary_validator import ItineraryValidator
from app.clients.hotel_routes import RoadRoute
from app.schemas.context import (AttractionContext, BusContext, HotelContext, HotelPriceContext,
                                 TrainContext, TripContext)
from app.schemas.itinerary import (Activity, DayPlan, HotelDecision, Itinerary,
                                   ItinerarySummary, TransportDecision)
from app.schemas.request import TripRequest
from app.services.hotel_recommendation import HotelRecommendationService


def _trip(budget="low"):
    return TripRequest(origin="Chennai", destination="Hyderabad",
        start_date=date(2026, 12, 10), end_date=date(2026, 12, 12),
        preferences={"budget": {"level": budget}})


def _itinerary():
    return Itinerary(summary=ItinerarySummary(origin="Chennai", destination="Hyderabad",
        days=2, travelers=1, pace="moderate", budget_level="low"),
        hotel=None, outbound_transport=TransportDecision(leg="Chennai to Hyderabad",
            mode="train", train_number="12760", arrival_station="Hyderabad Deccan"),
        days=[DayPlan(day=1, activities=[Activity(attraction_name=name)
            for name in ("Museum", "Palace", "Fort")])])


def _context(budget="low", hotel_b_price=1400):
    hotels = [HotelContext(id="edge", name="Edge Hotel", latitude=17.40, longitude=78.45,
        rating=4.8, review_count=6, price=HotelPriceContext(per_night=1200)),
        HotelContext(id="central", name="Central Hotel", latitude=17.39, longitude=78.47,
        rating=4.4, review_count=600, price=HotelPriceContext(per_night=hotel_b_price))]
    attractions = [AttractionContext(name=name, address="Hyderabad", latitude=17.38 + index * .01,
        longitude=78.47) for index, name in enumerate(("Museum", "Palace", "Fort"))]
    train = TrainContext(train_number="12760", train_name="Charminar Express",
        train_type="express", departure_time="07:00", arrival_time="18:00",
        duration_minutes=660, duration="11h", distance_km=700, lowest_fare=500,
        rating=4.0, has_pantry=False, to_station_name="Hyderabad Deccan Railway Station")
    return TripContext(trip=_trip(budget), hotels=hotels, attractions=attractions,
                       outbound_trains=[train])


class Routes:
    def __init__(self):
        self.calls = []

    async def matrix(self, origins, destinations):
        self.calls.append((origins, destinations))
        if len(origins) == 1 and len(destinations) == 1:
            return {(0, 0): RoadRoute(18, 7.2)}
        return {(i, j): RoadRoute(minutes, float(minutes) / 2)
                for i, origin in enumerate(origins)
                for j, minutes in enumerate((5, 5, 55) if origin[1] == 78.45
                                            else (20, 20, 20))}

    async def geocode_stop(self, stop, city):
        assert stop == "Hyderabad Deccan Railway Station"
        assert city == "Hyderabad"
        return (17.385, 78.48)


def test_balanced_hotel_wins_and_train_transfer_is_shown():
    async def run():
        context = _context()
        routes = Routes()
        itinerary = await HotelRecommendationService(routes).apply(_itinerary(), context)
        assert itinerary.hotel.hotel_id == "central"
        assert itinerary.hotel.price_per_night == 1400
        assert itinerary.hotel.avg_attraction_drive_minutes == 20
        assert itinerary.hotel.furthest_attraction_drive_minutes == 20
        assert itinerary.arrival_to_hotel.from_name == "Hyderabad Deccan Railway Station"
        assert itinerary.arrival_to_hotel.travel_minutes == 18
        assert "google.com/maps/dir" in itinerary.arrival_to_hotel.maps_url
        validated = ItineraryValidator().validate_and_calculate_costs(itinerary, context)
        assert validated.cost_breakdown.hotel_cost == 2800
        assert len(routes.calls) == 2
    asyncio.run(run())


def test_low_budget_excludes_over_budget_hotel_even_if_routes_are_better():
    async def run():
        context = _context(hotel_b_price=2400)
        itinerary = await HotelRecommendationService(Routes()).apply(_itinerary(), context)
        assert itinerary.hotel.hotel_id == "edge"
        assert itinerary.hotel.price_per_night == 1200
    asyncio.run(run())


def test_missing_routes_still_selects_sourced_hotel_without_claiming_drive_times():
    class UnavailableRoutes(Routes):
        async def matrix(self, origins, destinations):
            return {}
        async def geocode_stop(self, stop, city):
            return None
    async def run():
        itinerary = await HotelRecommendationService(UnavailableRoutes()).apply(
            _itinerary(), _context())
        assert itinerary.hotel.hotel_id in {"edge", "central"}
        assert itinerary.hotel.avg_attraction_drive_minutes is None
        assert "could not be verified" in itinerary.hotel.reasoning
        assert itinerary.arrival_to_hotel.travel_minutes is None
    asyncio.run(run())


def test_bus_transfer_uses_provider_drop_point_not_generic_city():
    class BusRoutes(Routes):
        async def geocode_stop(self, stop, city):
            assert stop == "MGBS Bus Station"
            return (17.38, 78.48)
    async def run():
        context = _context()
        context.outbound_buses = [BusContext(operator_name="TGSRTC",
            arrival_time="2026-12-10 09:00:00", dropping_point="MGBS Bus Station")]
        itinerary = _itinerary()
        itinerary.outbound_transport = TransportDecision(leg="Chennai to Hyderabad",
            mode="bus", operator_name="TGSRTC", arrival_station="Hyderabad")
        result = await HotelRecommendationService(BusRoutes()).apply(itinerary, context)
        assert result.arrival_to_hotel.from_name == "MGBS Bus Station"
        assert result.arrival_to_hotel.travel_minutes == 18
    asyncio.run(run())


def test_unknown_bus_drop_point_does_not_claim_a_route_time():
    async def run():
        context = _context()
        itinerary = _itinerary()
        itinerary.outbound_transport = TransportDecision(leg="Chennai to Hyderabad",
            mode="bus", operator_name="Unknown Bus", arrival_station="Hyderabad")
        result = await HotelRecommendationService(Routes()).apply(itinerary, context)
        assert result.arrival_to_hotel.travel_minutes is None
        assert "Confirm your exact arrival" in result.arrival_to_hotel.instruction
    asyncio.run(run())


def test_no_provider_hotel_removes_model_invention():
    async def run():
        context = TripContext(trip=_trip(), hotels=[])
        itinerary = _itinerary()
        itinerary.hotel = HotelDecision(hotel_id="invented", hotel_name="Fake Hotel",
                                        price_per_night=999)
        itinerary = await HotelRecommendationService(Routes()).apply(itinerary, context)
        assert itinerary.hotel is None
        assert itinerary.arrival_to_hotel is None
    asyncio.run(run())


def test_plan_endpoint_fills_hotel_when_model_returns_null(monkeypatch):
    async def run():
        plan_module = importlib.import_module("app.api.routes.plan")
        context = _context()
        class Orchestrator:
            async def build_context(self, trip):
                assert trip.destination == "Hyderabad"
                return context
        class Agent:
            async def plan(self, _context):
                return _itinerary()  # model omitted hotel
        monkeypatch.setattr(plan_module, "_orchestrator", Orchestrator())
        monkeypatch.setattr(plan_module, "_get_agent", lambda: Agent())
        monkeypatch.setattr(plan_module, "_hotel_recommendation",
                            HotelRecommendationService(Routes()))
        result = await plan_module.plan(context.trip)
        assert result.hotel.hotel_id == "central"
        assert result.hotel.price_per_night == 1400
        assert result.arrival_to_hotel.travel_minutes == 18
    asyncio.run(run())
