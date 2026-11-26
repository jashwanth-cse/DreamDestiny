import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.main import app
from app.schemas.conversation import UserSession, TripRecord, ItineraryVersionRecord
from app.schemas.conversation import RecoveryRunRecord
from app.storage.firestore_store import firestore_store
from app.storage.redis_store import redis_store
from app.whatsapp.client import whatsapp_client
from app.clients.planner_gateway import planner_gateway


def _webhook(message_id, body=None, button=None):
    message = {"id": message_id, "from": "919900000001", "timestamp": "1795710000"}
    if button:
        message.update(type="interactive", interactive={"type": "button_reply",
                       "button_reply": {"id": button, "title": body or button}})
    else:
        message.update(type="text", text={"body": body})
    return {"object": "whatsapp_business_account", "entry": [{"id": "test", "changes": [
        {"field": "messages", "value": {"messages": [message],
            "contacts": [{"wa_id": "919900000001", "profile": {"name": "Test Traveler"}}]}}]}]}


def _location_webhook(message_id):
    payload = _webhook(message_id, "placeholder")
    payload["entry"][0]["changes"][0]["value"]["messages"][0].update(
        type="location", location={"latitude": 17.378, "longitude": 78.48,
                                   "name": "MGBS bus station", "address": "Hyderabad"})
    payload["entry"][0]["changes"][0]["value"]["messages"][0].pop("text")
    return payload


def test_arrived_late_collects_pin_then_updates_nearby_stay_and_sights(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "app_env", "test")
        monkeypatch.setattr(settings, "trip_rescue_enabled", True)
        redis_store._client = None
        redis_store._memory_cache.clear()
        firestore_store._db = None
        firestore_store._trips.clear()
        firestore_store._itineraries.clear()
        firestore_store._recovery_runs.clear()
        whatsapp_client._sent_messages_log.clear()
        trip = TripRecord(wa_id="919900000001", conversation_id="conv_arrival", origin="Chennai",
            destination="Hyderabad", start_date="2026-11-26", end_date="2026-11-28",
            travelers=1, trip_request_data={"origin": "Chennai", "destination": "Hyderabad",
            "start_date": "2026-11-26", "end_date": "2026-11-28", "travelers": 1})
        await firestore_store.save_trip(trip)
        await firestore_store.save_itinerary_version(trip.wa_id, trip.trip_id,
            ItineraryVersionRecord(itinerary_data={"hotel": {"hotel_name": "Old suggestion"},
                "days": [{"day": 1, "activities": [{"attraction_name": "Far Museum"}]}]}))
        await redis_store.save_session(UserSession(wa_id=trip.wa_id, current_trip_id=trip.trip_id,
                                                  state="COMPLETED"))
        calls = []
        async def fake_recovery(*args):
            calls.append(args)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            return {"status": "ready", "change_kind": "arrival_delay",
                "location": {"latitude": 17.378, "longitude": 78.48, "address": "MGBS, Hyderabad"},
                "options": [{"id": "nearby:hotel:place-1", "category": "nearby_stay",
                    "title": "Nearby Hotel", "source_id": "place-1", "price": None,
                    "reason": "6 min drive", "warnings": ["Availability not verified"],
                    "maps_url": "https://maps.example/hotel",
                    "nearby_activities": [{"id": "sight-1", "name": "City Museum",
                                           "maps_url": "https://maps.example/museum"}],
                    "evidence": {"valid_until": expiry}}], "expires_at": expiry}
        monkeypatch.setattr(planner_gateway, "propose_recovery", fake_recovery)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for ident, payload in [
                ("a1", _webhook("a1", "Trip Rescue")),
                ("a2", _webhook("a2", "The bus was late and I reached Hyderabad by 9 am only")),
            ]:
                assert (await client.post("/webhook", json=payload)).status_code == 200
            assert not calls  # Arrival must ask for location before querying providers.
            assert "location" in str(whatsapp_client._sent_messages_log[-1]).lower()
            for ident, payload in [
                ("a3", _location_webhook("a3")),
                ("a4", _webhook("a4", "Option 1", "rescue_pick_0")),
                ("a5", _webhook("a5", "Apply update", "rescue_approve")),
            ]:
                assert (await client.post("/webhook", json=payload)).status_code == 200
        assert len(calls) == 2
        assert calls[0][-1]["latitude"] == 17.378
        latest = await firestore_store.get_latest_itinerary(trip.wa_id, trip.trip_id)
        assert latest.version_number == 2
        assert latest.itinerary_data["hotel"]["hotel_name"] == "Nearby Hotel"
        assert latest.itinerary_data["days"][0]["activities"][0]["attraction_name"] == "City Museum"
        assert "outbound_transport" not in latest.itinerary_data
    asyncio.run(run())


def test_nearby_itinerary_keeps_confirmed_activity_and_transport():
    from app.services.trip_rescue import _revised_itinerary
    trip = TripRecord(wa_id="owner", conversation_id="conv", origin="Chennai",
        destination="Hyderabad", start_date="2026-11-26", end_date="2026-11-28",
        travelers=1, trip_request_data={},
        commitments=[{"kind": "activity", "title": "Booked tour", "confirmed": True}])
    current = {"outbound_transport": {"mode": "bus", "operator_name": "Original"},
        "days": [{"day": 1, "activities": [
            {"attraction_name": "Booked tour"}, {"attraction_name": "Far attraction"}]}]}
    option = {"id": "nearby:hotel:place-1", "category": "nearby_stay",
        "source_id": "place-1", "title": "Nearby Hotel",
        "nearby_activities": [{"id": "sight-1", "name": "City Museum"}]}
    revised = _revised_itinerary(current, "I arrived late", option, trip)
    names = [a["attraction_name"] for a in revised["days"][0]["activities"]]
    assert names == ["Booked tour", "City Museum"]
    assert revised["outbound_transport"] == current["outbound_transport"]
    assert "hotel" not in current  # copy-on-write


def test_webhook_recovery_choice_approval_and_duplicate_delivery(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "app_env", "test")
        monkeypatch.setattr(settings, "trip_rescue_enabled", True)
        redis_store._client = None
        redis_store._memory_cache.clear()
        firestore_store._db = None
        firestore_store._trips.clear()
        firestore_store._itineraries.clear()
        firestore_store._recovery_runs.clear()
        whatsapp_client._sent_messages_log.clear()
        trip = TripRecord(wa_id="919900000001", conversation_id="conv_test", origin="Chennai",
                          destination="Madurai", start_date="2026-12-01", end_date="2026-12-03",
                          travelers=1, trip_request_data={"origin": "Chennai", "destination": "Madurai",
                              "start_date": "2026-12-01", "end_date": "2026-12-03", "travelers": 1})
        await firestore_store.save_trip(trip)
        await firestore_store.save_itinerary_version(trip.wa_id, trip.trip_id,
            ItineraryVersionRecord(itinerary_data={"days": [], "title": "Original"}))
        await redis_store.save_session(UserSession(wa_id=trip.wa_id, current_trip_id=trip.trip_id,
                                                  state="COMPLETED"))
        calls = []
        async def fake_recovery(*args):
            calls.append(args)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            return {"status": "ready", "change_kind": "delay", "options": [{
                "id": "outbound:bus:0", "title": "Verified Bus AC Sleeper", "price": 950,
                "reason": "Outbound bus option", "warnings": [],
                "evidence": {"valid_until": expiry}}], "expires_at": expiry}
        monkeypatch.setattr(planner_gateway, "propose_recovery", fake_recovery)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for ident, body, button in [
                ("m1", "Trip Rescue", None),
                ("m2", "My train was delayed 2 hours", None),
                ("m3", "Option 1", "rescue_pick_0"),
                ("m4", "Apply update", "rescue_approve"),
                ("m4", "Apply update", "rescue_approve"),
            ]:
                response = await client.post("/webhook", json=_webhook(ident, body, button))
                assert response.status_code == 200
        updated = await firestore_store.get_trip(trip.wa_id, trip.trip_id)
        latest = await firestore_store.get_latest_itinerary(trip.wa_id, trip.trip_id)
        assert updated.latest_version == 2
        assert latest.version_number == 2
        assert latest.itinerary_data["recovery_history"][0]["selected_option"]["id"] == "outbound:bus:0"
        assert latest.itinerary_data["outbound_transport"]["mode"] == "bus"
        assert len(calls) == 2  # proposal and fresh revalidation
        assert len(whatsapp_client._sent_messages_log) == 4
    asyncio.run(run())


def test_recovery_apply_rejects_stale_version_and_other_user():
    async def run():
        firestore_store._db = None
        firestore_store._trips.clear()
        firestore_store._itineraries.clear()
        firestore_store._recovery_runs.clear()
        trip = TripRecord(wa_id="owner", conversation_id="conv", origin="A", destination="B",
                          start_date="2026-12-01", end_date="2026-12-02", travelers=1,
                          trip_request_data={"origin": "A", "destination": "B",
                              "start_date": "2026-12-01", "end_date": "2026-12-02"})
        await firestore_store.save_trip(trip)
        previous = ItineraryVersionRecord(itinerary_data={"title": "old"})
        await firestore_store.save_itinerary_version("owner", trip.trip_id, previous)
        run = RecoveryRunRecord(wa_id="owner", trip_id=trip.trip_id, base_version=1,
                                change="train delayed", result={"status": "ready", "options": [{"id": "option:a"}, {"id": "option:b"}]})
        await firestore_store.save_recovery_run(run)
        assert await firestore_store.get_recovery_run("intruder", trip.trip_id, run.run_id) is None
        assert await firestore_store.apply_recovery(run, "option:a", previous, {"title": "new"}) == 2
        assert await firestore_store.apply_recovery(run, "option:a", previous, {"title": "new"}) == 2
        try:
            await firestore_store.apply_recovery(run, "option:b", previous, {"title": "bad"})
            assert False, "Different option must be rejected"
        except ValueError:
            pass
        newer = RecoveryRunRecord(wa_id="owner", trip_id=trip.trip_id, base_version=1,
                                  change="bus delayed", result={"status": "ready", "options": [{"id": "option:c"}]})
        await firestore_store.save_recovery_run(newer)
        try:
            await firestore_store.apply_recovery(newer, "option:c", previous, {"title": "stale"})
            assert False, "Stale version must be rejected"
        except ValueError:
            pass
        assert (await firestore_store.get_latest_itinerary("owner", trip.trip_id)).itinerary_data["title"] == "new"
    asyncio.run(run())


def test_price_change_during_approval_keeps_original_trip(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "app_env", "test")
        monkeypatch.setattr(settings, "trip_rescue_enabled", True)
        redis_store._client = None
        redis_store._memory_cache.clear()
        firestore_store._db = None
        firestore_store._trips.clear()
        firestore_store._itineraries.clear()
        firestore_store._recovery_runs.clear()
        trip = TripRecord(wa_id="919900000001", conversation_id="conv_test", origin="Chennai",
                          destination="Madurai", start_date="2026-12-01", end_date="2026-12-03",
                          travelers=1, trip_request_data={"origin": "Chennai", "destination": "Madurai",
                              "start_date": "2026-12-01", "end_date": "2026-12-03"})
        await firestore_store.save_trip(trip)
        await firestore_store.save_itinerary_version(trip.wa_id, trip.trip_id,
            ItineraryVersionRecord(itinerary_data={"title": "Original"}))
        await redis_store.save_session(UserSession(wa_id=trip.wa_id, current_trip_id=trip.trip_id,
                                                  state="COMPLETED"))
        counter = 0
        async def changing_price(*args):
            nonlocal counter
            counter += 1
            return {"status": "ready", "change_kind": "delay", "options": [{
                "id": "outbound:bus:0", "title": "Bus", "price": 950 if counter == 1 else 1200,
                "reason": "Outbound bus option", "warnings": []}],
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
        monkeypatch.setattr(planner_gateway, "propose_recovery", changing_price)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for ident, body, button in [("p1", "Trip Rescue", None),
                                        ("p2", "My train was delayed", None),
                                        ("p3", "Option 1", "rescue_pick_0"),
                                        ("p4", "Apply update", "rescue_approve")]:
                assert (await client.post("/webhook", json=_webhook(ident, body, button))).status_code == 200
        assert (await firestore_store.get_trip(trip.wa_id, trip.trip_id)).latest_version == 1
    asyncio.run(run())


def test_webhook_queues_before_ack_when_redis_available(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "app_env", "test")
        monkeypatch.setattr(settings, "trip_rescue_enabled", True)
        queued = []
        monkeypatch.setattr(redis_store, "_client", object())
        async def enqueue(payload):
            queued.append(payload)
            return "1-0"
        monkeypatch.setattr(redis_store, "enqueue_event", enqueue)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", json=_webhook("q1", "Trip Rescue"))
        assert response.status_code == 200
        assert len(queued) == 1
        assert '"message_id":"q1"' in queued[0]
        monkeypatch.setattr(redis_store, "_client", None)
    asyncio.run(run())
