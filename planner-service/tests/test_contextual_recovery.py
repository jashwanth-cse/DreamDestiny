import asyncio
from datetime import date, datetime, timezone

from app.recovery.contextual import ContextualRecoveryService
from app.recovery.models import RecoveryLocation, RecoveryRequest
from app.recovery.nearby import ResolvedLocation
from app.schemas.context import HotelContext, HotelPriceContext
from app.schemas.request import TripRequest


class ScriptedModel:
    def __init__(self, route, choice):
        self.route = route
        self.choice = choice
        self.calls = []

    async def generate_json(self, system_prompt, user_data, json_schema, max_tokens=8192):
        assert max_tokens <= 240
        self.calls.append(user_data)
        return self.route if len(self.calls) == 1 else self.choice


class SelectiveOrchestrator:
    def __init__(self):
        self.calls = []

    async def _get_hotels(self, city, check_in, check_out, adults, children, fresh=False):
        assert fresh is True
        self.calls.append("hotels")
        return [HotelContext(id="hotel-1", name="Verified Hotel",
                             price=HotelPriceContext(per_night=1800))]

    async def _get_buses(self, *args):
        raise AssertionError("Bus API was not needed")

    async def _get_trains(self, *args):
        raise AssertionError("Train API was not needed")

    async def _get_flights(self, *args):
        raise AssertionError("Flight API was not needed")

    async def _get_tourism(self, *args):
        raise AssertionError("Places attraction API was not needed")


class NearbyStub:
    async def search(self, current, destination):
        return (ResolvedLocation(17.4, 78.4, "MGBS"),
                [{"id": "place-1", "name": "Nearby Hotel", "travel_minutes": 6,
                  "distance_km": 2.0, "maps_url": "https://maps.example/hotel"}],
                [{"id": "sight-1", "name": "City Museum", "travel_minutes": 10,
                  "distance_km": 3.1, "maps_url": "https://maps.example/museum"}])


def _trip():
    return TripRequest(origin="Chennai", destination="Hyderabad",
                       start_date=date(2026, 11, 26), end_date=date(2026, 11, 28))


def test_arbitrary_hotel_problem_routes_to_serp_only_and_rejects_invented_id():
    async def run():
        model = ScriptedModel(
            {"kind": "stay_problem", "tools": ["mobility", "hotels"],
             "direction": "outbound", "needs_location": False},
            {"id": "invented:hotel", "why": "A confirmed room costs 100", "activity_to_replace": None})
        orchestrator = SelectiveOrchestrator()
        service = ContextualRecoveryService(orchestrator, model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc))
        result = await service.recover(RecoveryRequest(
            trip=_trip(), change="The hotel room smells bad and I need a different stay"))
        assert orchestrator.calls == ["hotels"]
        assert len(model.calls) == 2
        assert result.status == "ready"
        assert result.recommended_option_id == "hotel:hotel-1"
        assert result.options[0].price == 1800
        assert "confirmed room" not in result.response_text.lower()
        assert "supplier booking" in result.response_text.lower()
    asyncio.run(run())


def test_arrived_late_overrides_wrong_model_route_and_asks_for_location():
    async def run():
        model = ScriptedModel(
            {"kind": "delay", "tools": ["mobility"], "direction": "outbound",
             "needs_location": False},
            {"id": "nearby:hotel:place-1", "why": "Nearby", "activity_to_replace": None})
        service = ContextualRecoveryService(SelectiveOrchestrator(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc), nearby=NearbyStub())
        request = RecoveryRequest(trip=_trip(),
            change="The bus was late and I reached Hyderabad by 9 am")
        first = await service.recover(request)
        assert first.status == "needs_clarification"
        assert first.change_kind == "arrival_delay"
        assert len(model.calls) == 1
        model.calls.clear()
        result = await service.recover(request.model_copy(update={
            "current_location": RecoveryLocation(latitude=17.4, longitude=78.4)}))
        assert result.status == "ready"
        assert result.recommended_option_id.startswith("nearby:hotel:")
        assert result.options[0].nearby_activities[0]["name"] == "City Museum"
        assert "City Museum (10 min drive)" in result.response_text
        assert all(not option.id.startswith("outbound:") for option in result.options)
    asyncio.run(run())


def test_near_me_requires_pin_even_when_model_requests_city_hotels():
    async def run():
        model = ScriptedModel(
            {"kind": "stay_problem", "tools": ["hotels"], "direction": "outbound",
             "needs_location": False},
            {"id": "nearby:hotel:place-1", "why": "Nearby", "activity_to_replace": None})
        service = ContextualRecoveryService(SelectiveOrchestrator(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc), nearby=NearbyStub())
        result = await service.recover(RecoveryRequest(
            trip=_trip(), change="I need the nearest hotel near me"))
        assert result.status == "needs_clarification"
        assert "location" in result.clarification.lower()
        assert len(model.calls) == 1
    asyncio.run(run())


def test_model_requested_location_switches_city_hotels_to_nearby_search():
    async def run():
        model = ScriptedModel(
            {"kind": "stay_problem", "tools": ["hotels"], "direction": "outbound",
             "needs_location": True},
            {"id": "nearby:hotel:place-1", "why": "Nearby", "activity_to_replace": None})
        service = ContextualRecoveryService(SelectiveOrchestrator(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc), nearby=NearbyStub())
        base = RecoveryRequest(trip=_trip(), change="My hotel room is dirty")
        first = await service.recover(base)
        assert first.status == "needs_clarification"
        model.calls.clear()
        second = await service.recover(base.model_copy(update={
            "current_location": RecoveryLocation(latitude=17.4, longitude=78.4)}))
        assert second.recommended_option_id == "nearby:hotel:place-1"
    asyncio.run(run())


def test_invalid_model_choice_with_multiple_candidates_does_not_auto_update():
    async def run():
        class TwoHotels(SelectiveOrchestrator):
            async def _get_hotels(self, city, check_in, check_out, adults, children, fresh=False):
                self.calls.append("hotels")
                return [HotelContext(id=ident, name=name,
                    price=HotelPriceContext(per_night=1800))
                    for ident, name in (("h1", "Hotel One"), ("h2", "Hotel Two"))]
        model = ScriptedModel(
            {"kind": "stay_problem", "tools": ["hotels"], "direction": "outbound",
             "needs_location": False},
            {"id": "invented:hotel", "why": "Guaranteed room", "activity_to_replace": None})
        result = await ContextualRecoveryService(TwoHotels(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc)).recover(
                RecoveryRequest(trip=_trip(), change="I need a different hotel"))
        assert result.status == "no_verified_options"
        assert result.recommended_option_id is None
    asyncio.run(run())


def test_contextual_place_delay_ignores_model_request_for_transport():
    async def run():
        model = ScriptedModel(
            {"kind": "delay", "tools": ["mobility"], "direction": "outbound",
             "needs_location": False},
            {"id": "nearby:activity:sight-1", "why": "10 min drive",
             "activity_to_replace": None})
        service = ContextualRecoveryService(SelectiveOrchestrator(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc), nearby=NearbyStub())
        result = await service.recover(RecoveryRequest(trip=_trip(),
            change="there was a delay at chomanah palace and the time is 4 oclock now",
            extracted_fields={"disruption_type": "delayed", "affected_item": "place"},
            current_location=RecoveryLocation(address="Chowmahalla Palace, Hyderabad")))
        assert result.status == "ready"
        assert result.change_kind == "place_delay"
        assert result.recommended_option_id == "nearby:activity:sight-1"
        assert all(o.category == "experience" for o in result.options)
    asyncio.run(run())
