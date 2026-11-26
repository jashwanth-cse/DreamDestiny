import asyncio

import httpx

from services import google_places


def test_rescue_search_skips_photo_calls_and_does_not_poison_normal_cache(monkeypatch):
    async def run():
        requests = []
        def handler(request):
            requests.append(request)
            assert "places:searchText" in str(request.url)
            assert "places.photos" not in request.headers["X-Goog-FieldMask"]
            return httpx.Response(200, json={"places": [{
                "id": "place-1", "displayName": {"text": "Museum"},
                "photos": [{"name": "photos/p1"}],
                "location": {"latitude": 17.4, "longitude": 78.4}}]})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async def get_client():
            return client
        async def forbidden(*args, **kwargs):
            raise AssertionError("A fresh rescue request must not read or overwrite the normal cache")
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
        monkeypatch.setattr(google_places, "_get_http_client", get_client)
        monkeypatch.setattr(google_places, "_cache_get", forbidden)
        monkeypatch.setattr(google_places, "_cache_set", forbidden)
        result = await google_places.fetch_tourist_attractions("Hyderabad", fresh=True)
        assert len(requests) == 1
        assert result[0]["name"] == "Museum"
        assert result[0]["image_url"] is None
        await client.aclose()
    asyncio.run(run())
