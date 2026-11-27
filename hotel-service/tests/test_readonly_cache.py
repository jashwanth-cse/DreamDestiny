"""A readonly SQLite cache must never erase a valid hotel search response."""

import os
import sqlite3
from datetime import date, timedelta

os.environ.setdefault("SERPAPI_API_KEY", "test-key")

from fastapi.testclient import TestClient
from app.main import app
from app.routes import hotels as route


def test_hotel_search_survives_readonly_cache(monkeypatch):
    async def provider(**_kwargs):
        return [{"id": "hotel-1", "name": "Kochi Stay",
                 "price": {"per_night": 2200, "currency": "INR"}}]

    def readonly(*_args, **_kwargs):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(route, "fetch_hotels", provider)
    monkeypatch.setattr(route, "get_cached", readonly)
    monkeypatch.setattr(route, "set_cached", readonly)
    start = date.today() + timedelta(days=14)
    response = TestClient(app).get("/hotels", params={
        "city": "Kochi", "check_in": start.isoformat(),
        "check_out": (start + timedelta(days=2)).isoformat(), "adults": 1})
    assert response.status_code == 200
    assert response.json()["hotels"][0]["name"] == "Kochi Stay"
