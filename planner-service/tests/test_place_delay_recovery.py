import asyncio
from datetime import date, datetime, timezone
import httpx

from app.recovery.models import RecoveryLocation, RecoveryRequest
from app.recovery.service import RecoveryService
from app.recovery.nearby import ResolvedLocation
from app.recovery.nearby import NearbyProvider
from app.schemas.request import TripRequest


class NoTransportOrchestrator:
    async def build_context(self, *_args):
        raise AssertionError("A place delay must not search intercity transport")


class NearbyPlaces:
    async def search(self, current, destination):
        assert destination == "Hyderabad"
        assert "Chowmahalla Palace" in current.address
        return (ResolvedLocation(17.36, 78.47, "Chowmahalla Palace, Hyderabad"),
                [{"id": "hotel-1", "name": "Hotel One", "travel_minutes": 5,
                  "distance_km": 1, "maps_url": "https://maps.example/hotel"}],
                [{"id": "palace", "name": "Chowmahalla Palace", "travel_minutes": 0,
                  "distance_km": 0, "maps_url": "https://maps.example/palace"},
                 {"id": "museum", "name": "Nearby Museum", "travel_minutes": 12,
                  "distance_km": 3, "maps_url": "https://maps.example/museum"}])


def test_palace_delay_uses_itinerary_place_and_only_nearby_sightseeing():
    async def run():
        request = RecoveryRequest(
            trip=TripRequest(origin="Chennai", destination="Hyderabad",
                start_date=date(2026, 11, 26), end_date=date(2026, 11, 28)),
            itinerary={"days": [{"date": "2026-11-26", "activities": [
                {"attraction_name": "Chowmahalla Palace", "start_time": "15:00"}]}]},
            change="there was a delay at chomanah palace and the time is 4 oclock now",
            extracted_fields={"disruption_type": "delayed", "affected_item": "place"},
            current_location=RecoveryLocation(address="Chowmahalla Palace, Hyderabad"))
        result = await RecoveryService(NoTransportOrchestrator(), object(),
            now=lambda: datetime(2026, 11, 26, 10, 30, tzinfo=timezone.utc),
            nearby=NearbyPlaces()).recover(request)
        assert result.status == "ready"
        assert result.change_kind == "place_delay"
        assert [o.title for o in result.options] == ["Nearby Museum"]
        assert all(o.id.startswith("nearby:activity:") for o in result.options)
    asyncio.run(run())


def test_places_rejects_travel_agency_misclassified_as_attraction():
    async def run():
        def handler(_request):
            return httpx.Response(200, json={"places": [
                {"id": "agency", "displayName": {"text": "Khan Travels"},
                 "location": {"latitude": 17.36, "longitude": 78.47},
                 "primaryType": "tourist_attraction", "types": ["tourist_attraction"]},
                {"id": "museum", "displayName": {"text": "Nizams Art Gallery"},
                 "location": {"latitude": 17.36, "longitude": 78.47},
                 "primaryType": "art_gallery", "types": ["tourist_attraction", "art_gallery"]}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            places = await NearbyProvider("test-key")._places(client,
                ResolvedLocation(17.36, 78.47, "Palace"), "tourist_attraction")
        assert [place["name"] for place in places] == ["Nizams Art Gallery"]
    asyncio.run(run())
