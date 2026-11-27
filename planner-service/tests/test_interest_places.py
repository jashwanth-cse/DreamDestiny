"""Targeted Places results must be real, local, open museum records."""

from datetime import date

from app.clients import interest_places
from app.schemas.context import TripContext
from app.schemas.request import TripRequest


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"places": [
            {"id": "google-1", "displayName": {"text": "Salar Jung Museum"},
             "formattedAddress": "Hyderabad, Telangana, India",
             "location": {"latitude": 17.37, "longitude": 78.48},
             "rating": 4.6, "userRatingCount": 2000,
             "regularOpeningHours": {"periods": []}, "businessStatus": "OPERATIONAL"},
            {"id": "google-2", "displayName": {"text": "Other Museum"},
             "formattedAddress": "Delhi, India"},
            {"id": "google-3", "displayName": {"text": "Closed Museum"},
             "formattedAddress": "Hyderabad, India", "businessStatus": "CLOSED_PERMANENTLY"},
        ]}


class Client:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, json, headers):
        assert json["textQuery"] == "museums in Hyderabad, India"
        assert "regularOpeningHours" in headers["X-Goog-FieldMask"]
        return Response()


def test_requested_museums_only_add_city_matches(monkeypatch):
    monkeypatch.setattr(interest_places.settings, "google_maps_api_key", "test-key")
    monkeypatch.setattr(interest_places.httpx, "AsyncClient", Client)
    trip = TripRequest(origin="Chennai", destination="Hyderabad",
        start_date=date(2026, 12, 20), end_date=date(2026, 12, 22),
        preferences={"activities": {"interests": ["museums"]}})
    context = TripContext(trip=trip)
    coroutine = interest_places.InterestPlacesClient().add_requested_places(context)
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    assert len(context.attractions) == 1
    assert context.attractions[0].name == "Salar Jung Museum"
    assert context.attractions[0].place_id == "google-1"
