import asyncio
from datetime import date, datetime, timezone

import httpx

from app.recovery.agents import classify_change
from app.recovery.models import RecoveryLocation, RecoveryRequest
from app.recovery.nearby import NearbyProvider, ResolvedLocation
from app.recovery.nearby import NearbySearchError
from app.recovery.service import RecoveryService
from app.schemas.request import TripRequest


class FirstChoiceModel:
    def __init__(self):
        self.calls = 0

    async def generate_json(self, system_prompt, user_data, json_schema):
        self.calls += 1
        return {"ids": [user_data["candidates"][0]["id"]]}


class NoOutboundOrchestrator:
    async def build_context(self, trip):
        raise AssertionError("An arrived traveler must not search outbound transport")


class FakeNearby:
    async def search(self, current, destination):
        assert destination == "Hyderabad"
        assert current.latitude == 17.4
        return (ResolvedLocation(17.4, 78.4, "MGBS, Hyderabad"),
                [{"id": "hotel-1", "name": "Nearby Hotel", "travel_minutes": 6,
                  "distance_km": 2.1, "maps_url": "https://maps.example/hotel"}],
                [{"id": "sight-1", "name": "City Museum", "travel_minutes": 9,
                  "distance_km": 3.0, "maps_url": "https://maps.example/sight"}])


def test_arrived_late_asks_location_then_uses_local_agents_only():
    async def run():
        model = FirstChoiceModel()
        service = RecoveryService(NoOutboundOrchestrator(), model,
            now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc), nearby=FakeNearby())
        base = dict(trip=TripRequest(origin="Chennai", destination="Hyderabad",
                    start_date=date(2026, 11, 26), end_date=date(2026, 11, 28)),
                    change="The bus was late and I reached Hyderabad by 9 am only")
        assert classify_change(base["change"]) == "arrival_delay"
        clarification = await service.recover(RecoveryRequest(**base))
        assert clarification.status == "needs_clarification"
        assert "location" in clarification.clarification.lower()
        result = await service.recover(RecoveryRequest(
            **base, current_location=RecoveryLocation(latitude=17.4, longitude=78.4)))
        assert result.status == "ready"
        assert result.change_kind == "arrival_delay"
        assert result.options[0].category == "nearby_stay"
        assert result.options[0].travel_minutes == 6
        assert result.options[0].price is None
        assert result.options[0].nearby_activities[0]["name"] == "City Museum"
        assert [t.agent for t in result.traces] == ["nearby_stay", "nearby_experience"]
        assert model.calls == 2
        assert all(not o.id.startswith("outbound:") for o in result.options)
    asyncio.run(run())


def test_google_nearby_uses_place_types_and_route_eta(monkeypatch):
    async def run():
        requests = []
        def handler(request):
            requests.append(request)
            if "geocode" in str(request.url):
                address = request.url.params["address"]
                point = {"lat": 17.4, "lng": 78.4} if "MGBS" in address else {"lat": 17.38, "lng": 78.49}
                return httpx.Response(200, json={"status": "OK", "results": [{
                    "formatted_address": address, "types": ["establishment"],
                    "geometry": {"location": point}}]})
            if "places:searchNearby" in str(request.url):
                import json
                kind = json.loads(request.content)["includedTypes"][0]
                ident = "hotel" if kind == "hotel" else "sight"
                return httpx.Response(200, json={"places": [{"id": ident,
                    "displayName": {"text": ident.title()},
                    "location": {"latitude": 17.41, "longitude": 78.41}}]})
            if "computeRouteMatrix" in str(request.url):
                return httpx.Response(200, json=[
                    {"destinationIndex": 0, "condition": "ROUTE_EXISTS", "distanceMeters": 1800, "duration": "360s"},
                    {"destinationIndex": 1, "condition": "ROUTE_EXISTS", "distanceMeters": 3200, "duration": "540s"},
                ])
            raise AssertionError(request.url)
        original = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: original(
            transport=httpx.MockTransport(handler)))
        location, hotels, sights = await NearbyProvider("test-key").search(
            RecoveryLocation(address="MGBS bus stand"), "Hyderabad")
        assert location.latitude == 17.4
        assert hotels[0]["travel_minutes"] == 6
        assert sights[0]["travel_minutes"] == 9
        assert len(requests) == 5  # destination, landmark, two Places searches, one route matrix
    asyncio.run(run())


def test_outside_destination_pin_is_rejected_before_places_lookup(monkeypatch):
    async def run():
        def handler(request):
            assert "geocode" in str(request.url)
            return httpx.Response(200, json={"status": "OK", "results": [{
                "formatted_address": "Hyderabad, India", "types": ["locality"],
                "geometry": {"location": {"lat": 17.38, "lng": 78.49}}}]})
        original = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: original(
            transport=httpx.MockTransport(handler)))
        try:
            await NearbyProvider("test-key").search(
                RecoveryLocation(latitude=28.61, longitude=77.21), "Hyderabad")
            assert False, "A Delhi pin must not produce Hyderabad hotels"
        except NearbySearchError as exc:
            assert "outside Hyderabad" in str(exc)
    asyncio.run(run())
