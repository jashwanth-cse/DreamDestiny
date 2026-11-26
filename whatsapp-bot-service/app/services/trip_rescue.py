"""Opt-in WhatsApp Trip Rescue journey, isolated from the existing planner flow."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import hashlib
import json
import copy
import uuid

from app.clients.planner_gateway import planner_gateway, PlannerGatewayError
from app.schemas.conversation import (ConversationState, ItineraryVersionRecord,
                                      RecoveryRunRecord, UserSession)
from app.schemas.webhook import NormalizedEvent
from app.schemas.trip import TripRequest
from app.storage.firestore_store import firestore_store
from app.storage.redis_store import redis_store
from app.whatsapp.client import whatsapp_client
from app.whatsapp.messages import build_button_message, build_text_message

logger = logging.getLogger(__name__)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs a timezone offset")
    return parsed.astimezone(timezone.utc)


def _commitments_digest(items: list[dict]) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _revised_itinerary(current: dict, change: str, option: dict, trip) -> dict:
    """Apply only the selected recommendation, preserving unrelated itinerary data."""
    revised = copy.deepcopy(current)
    option_id = option["id"]
    if option_id.startswith(("outbound:", "return:")):
        direction, mode, _ = option_id.split(":", 2)
        prior = revised.get(f"{direction}_transport") or {}
        decision = {
            "leg": prior.get("leg") or f"{trip.origin} to {trip.destination}",
            "mode": mode,
            "departure_time": option.get("departure_time"),
            "arrival_time": option.get("arrival_time"),
            "fare_per_person": option.get("price"),
            "reasoning": "Trip Rescue recommendation; supplier booking unchanged",
        }
        if mode == "train":
            decision["train_number"] = option.get("source_id")
            decision["travel_class"] = option_id.rsplit(":", 1)[-1]
        elif mode == "flight":
            decision["flight_id"] = option.get("source_id")
        elif mode == "bus":
            decision["operator_name"] = option.get("title")
        revised[f"{direction}_transport"] = decision
    elif option_id.startswith("activity:"):
        for day in revised.get("days", []):
            for activity in day.get("activities", []):
                old_name = activity.get("attraction_name", "")
                if old_name and old_name.casefold() in change.casefold():
                    activity.update(attraction_name=option["title"], start_time=None,
                                    duration_minutes=None, estimated_cost=None,
                                    notes="Alternative suggestion; confirm opening hours before visiting")
                    break
    revised.setdefault("recovery_history", []).append({
        "change": change, "selected_option": option,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "note": "Itinerary recommendation only; supplier bookings unchanged",
    })
    return revised


class TripRescueService:
    async def _send(self, session: UserSession, message: str, buttons=None):
        payload = (build_button_message(session.wa_id, message, buttons)
                   if buttons else build_text_message(session.wa_id, message))
        if not await whatsapp_client.send_message_payload(payload):
            raise RuntimeError("WhatsApp send failed")

    async def handle(self, session: UserSession, event: NormalizedEvent) -> bool:
        text = (event.text or "").strip()
        lower = text.casefold()
        payload = event.payload_id or ""
        active = session.state in {ConversationState.RECOVERY_CHANGE,
                                   ConversationState.RECOVERY_CHOICE,
                                   ConversationState.RECOVERY_APPROVAL}
        trigger = lower in {"trip rescue", "something changed", "replan my trip"} or payload == "btn_trip_rescue"
        booking = lower.startswith("booking add:")
        if not (active or trigger or booking):
            return False

        if lower in {"cancel", "menu", "stop"} or payload == "rescue_cancel":
            session.state = ConversationState.COMPLETED
            session.pending_recovery_id = None
            session.pending_recovery_option_id = None
            await redis_store.save_session(session)
            await self._send(session, "Trip Rescue cancelled. Your saved itinerary was not changed.")
            return True

        trip = await firestore_store.get_trip(session.wa_id, session.current_trip_id) if session.current_trip_id else None
        if not trip:
            trip = await firestore_store.get_latest_trip(session.wa_id)
            if trip:
                session.current_trip_id = trip.trip_id
        if not trip:
            await self._send(session, "I couldn't find a saved trip. Reply *New trip* to plan one first.")
            return True

        if booking:
            # Explicit manual import. The traveler is the source; no supplier confirmation is implied.
            parts = [p.strip() for p in text.split(":", 1)[1].split("|")]
            try:
                if len(parts) != 5 or parts[0].lower() not in {"transport", "stay", "activity", "other"}:
                    raise ValueError("format")
                start, end = _utc(parts[2]), _utc(parts[3])
                cost = float(parts[4])
                if end <= start or cost < 0 or not parts[1]:
                    raise ValueError("values")
            except (ValueError, OverflowError):
                await self._send(session, "Use: *Booking add: transport | Train 123 | 2026-12-01T09:00+05:30 | 2026-12-01T15:00+05:30 | 1200*. Times need an offset. This records a booking you report; it does not verify it with the supplier.")
                return True
            trip.commitments.append({"id": f"c_{uuid.uuid4().hex[:10]}", "kind": parts[0].lower(),
                                     "title": parts[1], "starts_at": start.isoformat(),
                                     "ends_at": end.isoformat(), "confirmed": True,
                                     "cost": cost, "currency": "INR", "notes": "Traveler reported"})
            await firestore_store.save_trip(trip)
            session.pending_recovery_id = None
            session.pending_recovery_option_id = None
            session.state = ConversationState.COMPLETED
            await redis_store.save_session(session)
            await self._send(session, f"Saved your reported booking: *{parts[1]}*. Reply *Trip Rescue* if plans change.")
            return True

        if trigger:
            session.state = ConversationState.RECOVERY_CHANGE
            await redis_store.save_session(session)
            await self._send(session, f"What changed on your trip to *{trip.destination}*? Include the affected train, flight, hotel, or place and the new timing if known.")
            return True

        if session.state == ConversationState.RECOVERY_CHANGE:
            version = await firestore_store.get_latest_itinerary(session.wa_id, trip.trip_id)
            if not version:
                await self._send(session, "The saved itinerary is unavailable. Please try again later.")
                return True
            try:
                request = TripRequest.model_validate(trip.trip_request_data)
                result = await planner_gateway.propose_recovery(request, version.itinerary_data,
                                                                text, trip.commitments, trip.trip_id,
                                                                session.correlation_id)
            except (PlannerGatewayError, ValueError):
                await self._send(session, "I couldn't check current alternatives. Your itinerary is unchanged. Please try again shortly.")
                return True
            if result.get("status") == "needs_clarification":
                await self._send(session, result.get("clarification") or "Please describe what changed.")
                return True
            options = result.get("options") or []
            if result.get("status") != "ready" or not options:
                await self._send(session, "I couldn't find a source-backed alternative right now. Your itinerary is unchanged. Try a different route or contact your provider.")
                return True
            run = RecoveryRunRecord(wa_id=session.wa_id, trip_id=trip.trip_id,
                                    base_version=trip.latest_version, change=text, result=result,
                                    commitments_digest=_commitments_digest(trip.commitments))
            await firestore_store.save_recovery_run(run)
            session.pending_recovery_id = run.run_id
            session.state = ConversationState.RECOVERY_CHOICE
            await redis_store.save_session(session)
            lines = ["*Trip Rescue options* (search results, not bookings):"]
            for i, option in enumerate(options[:3], 1):
                price = f"₹{option['price']:,.0f}" if option.get("price") is not None else "price unknown"
                warnings = "; ".join(option.get("warnings") or [])
                lines.append(f"{i}. *{option['title']}* — {price}. {option.get('reason', '')} {warnings}")
            lines.append("Choose an option to review. Availability and prices may change.")
            buttons = [(f"rescue_pick_{i}", f"Option {i+1}") for i in range(min(3, len(options)))]
            await self._send(session, "\n".join(lines), buttons)
            return True

        run = (await firestore_store.get_recovery_run(session.wa_id, trip.trip_id, session.pending_recovery_id)
               if session.pending_recovery_id else None)
        if run and run.status == "applied":
            session.state = ConversationState.COMPLETED
            await redis_store.save_session(session)
            await self._send(session, f"This choice was already applied to itinerary version {run.applied_version}. No supplier booking was changed.")
            return True
        if not run or run.status != "proposed":
            session.state = ConversationState.COMPLETED
            await redis_store.save_session(session)
            await self._send(session, "These options are no longer active. Reply *Trip Rescue* to refresh them.")
            return True
        expiry = run.result.get("expires_at")
        if expiry and _utc(expiry) <= datetime.now(timezone.utc):
            session.state = ConversationState.RECOVERY_CHANGE
            await redis_store.save_session(session)
            await self._send(session, "These options expired. Tell me what changed again to refresh them.")
            return True

        if session.state == ConversationState.RECOVERY_CHOICE:
            index = None
            if payload.startswith("rescue_pick_"):
                try:
                    index = int(payload.removeprefix("rescue_pick_"))
                except ValueError:
                    pass
            elif lower in {"1", "2", "3"}:
                index = int(lower) - 1
            options = run.result.get("options") or []
            if index is None or index < 0 or index >= len(options):
                await self._send(session, "Please tap one of the options, or reply 1, 2, or 3.")
                return True
            option = options[index]
            session.pending_recovery_option_id = option["id"]
            session.state = ConversationState.RECOVERY_APPROVAL
            await redis_store.save_session(session)
            await self._send(session, f"Apply *{option['title']}* to your saved itinerary? This records your choice only. It does not buy, cancel, or change any supplier booking.",
                             [("rescue_approve", "Apply update"), ("rescue_cancel", "Cancel")])
            return True

        if session.state == ConversationState.RECOVERY_APPROVAL:
            if payload != "rescue_approve" and lower not in {"apply update", "approve"}:
                await self._send(session, "Tap *Apply update* to revise your saved itinerary, or *Cancel* to keep it as is.")
                return True
            option = next((o for o in run.result.get("options", []) if o["id"] == session.pending_recovery_option_id), None)
            if not option:
                await self._send(session, "That option is unavailable. Reply *Trip Rescue* to start again.")
                return True
            # Recheck price and existence with a fresh provider query before applying.
            current = await firestore_store.get_latest_itinerary(session.wa_id, trip.trip_id)
            if not current or trip.latest_version != run.base_version:
                await self._send(session, "Your trip has changed since these options were generated. Reply *Trip Rescue* to refresh them.")
                return True
            if run.commitments_digest and run.commitments_digest != _commitments_digest(trip.commitments):
                await self._send(session, "Your reported bookings changed. Reply *Trip Rescue* to refresh the options.")
                return True
            try:
                refreshed = await planner_gateway.propose_recovery(
                    TripRequest.model_validate(trip.trip_request_data), current.itinerary_data,
                    run.change, trip.commitments, trip.trip_id, session.correlation_id)
                fresh_option = next((o for o in refreshed.get("options", []) if o["id"] == option["id"]), None)
                if not fresh_option or any(fresh_option.get(k) != option.get(k) for k in
                    ("price", "currency", "departure_time", "arrival_time", "source_id", "warnings")):
                    raise ValueError("Option or price changed")
                revised = _revised_itinerary(current.itinerary_data, run.change, fresh_option, trip)
                new_version = await firestore_store.apply_recovery(run, option["id"], current, revised)
                try:
                    await redis_store.update_archived_trip(session.wa_id, trip.trip_id, revised)
                except Exception:
                    logger.warning("My Trips cache update failed for trip %s", trip.trip_id, exc_info=True)
            except (PlannerGatewayError, ValueError):
                await self._send(session, "The option could not be reverified or the trip changed. No supplier booking was made. Reply *Trip Rescue* to refresh.")
                return True
            session.state = ConversationState.COMPLETED
            session.pending_recovery_id = None
            session.pending_recovery_option_id = None
            await redis_store.save_session(session)
            await self._send(session, f"Saved itinerary version {new_version}: *{option['title']}*. Your supplier bookings have not changed; confirm any purchase or cancellation with the provider.")
            return True
        return False


trip_rescue_service = TripRescueService()
