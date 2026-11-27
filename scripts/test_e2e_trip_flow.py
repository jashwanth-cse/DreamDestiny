"""Real-provider, real-Bedrock WhatsApp trip and rescue replay.

Run from repository root: python scripts/test_e2e_trip_flow.py
The JSONL trace records prompts and responses, but never credentials. This
uses the deployed provider APIs and Bedrock; it does not send Meta messages or
write to a user's Firestore trip.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
for key, value in dotenv_values(ROOT / ".env").items():
    if value and key not in os.environ:
        os.environ[key] = value
sys.path.insert(0, str(ROOT / "planner-service"))

from app.agents.planning_agent import PlanningAgent
from app.business.itinerary_validator import ItineraryValidator
from app.clients.flight_client import FlightClient
from app.clients.hotel_client import HotelClient
from app.clients.interest_places import InterestPlacesClient
from app.clients.hotel_routes import HotelRoutesClient
from app.clients.route_client import RouteClient
from app.clients.tourism_client import TourismClient
from app.clients.transport_client import BusClient, TrainClient
from app.config import settings
from app.orchestration.trip_orchestrator import TripOrchestrator
from app.recovery.interpreter import ConverseRescueClient, RescueExtractionRequest
from app.recovery.models import RecoveryRequest
from app.recovery.service import RecoveryService
from app.schemas.request import TripRequest
from app.services.hotel_recommendation import HotelRecommendationService
from app.services.schedule_verifier import ScheduleVerifier
from app.services.llm.llm_client import BedrockLLMClient


def load_file_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


whatsapp_trip = load_file_module("e2e_whatsapp_trip", ROOT / "whatsapp-bot-service/app/schemas/trip.py")
whatsapp_messages = load_file_module("e2e_whatsapp_messages", ROOT / "whatsapp-bot-service/app/whatsapp/messages.py")


def jsonable(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Trace:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w", encoding="utf-8")

    def log(self, scenario: str, step: str, **data):
        entry = {"at": datetime.now(timezone.utc).isoformat(),
                 "scenario": scenario, "step": step, **jsonable(data)}
        self.file.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


class TracedProvider:
    """Log actual calls and returned provider records without substituting data."""
    def __init__(self, name, delegate, trace, scenario):
        self.name, self.delegate, self.trace, self.scenario = name, delegate, trace, scenario

    _gateway_lock = asyncio.Lock()
    _last_gateway_call = 0.0

    def __getattr__(self, method):
        real = getattr(self.delegate, method)
        async def invoke(*args, **kwargs):
            async with self._gateway_lock:
                # Public gateway limits expensive provider endpoints to 2 r/s.
                pause = max(0.0, 0.8 - (time.perf_counter() - TracedProvider._last_gateway_call))
                if pause:
                    await asyncio.sleep(pause)
                TracedProvider._last_gateway_call = time.perf_counter()
                start = time.perf_counter()
                self.trace.log(self.scenario, "tool_call", tool=self.name, method=method,
                               args=args, kwargs=kwargs)
                try:
                    output = await real(*args, **kwargs)
                    self.trace.log(self.scenario, "tool_result", tool=self.name, method=method,
                                   latency_ms=round((time.perf_counter()-start)*1000), output=output)
                    return output
                except Exception as exc:
                    self.trace.log(self.scenario, "tool_error", tool=self.name, method=method,
                                   latency_ms=round((time.perf_counter()-start)*1000), error=repr(exc))
                    raise
        return invoke


class TracedBedrock(BedrockLLMClient):
    def __init__(self, trace, scenario):
        super().__init__()
        self.trace, self.scenario = trace, scenario

    def on_raw_text(self, raw_text):
        self.trace.log(self.scenario, "llm_raw_text", raw_output=raw_text)

    async def generate_json(self, system_prompt, user_data, json_schema,
                            max_tokens=8192, temperature=0.2):
        start = time.perf_counter()
        self.trace.log(self.scenario, "llm_prompt", model=self._model,
                       system_prompt=system_prompt, user_data=user_data,
                       json_schema=json_schema, max_tokens=max_tokens,
                       temperature=temperature)
        try:
            raw = await super().generate_json(system_prompt, user_data, json_schema,
                                             max_tokens, temperature)
            self.trace.log(self.scenario, "llm_raw_json", latency_ms=round((time.perf_counter()-start)*1000),
                           raw_output=raw)
            return raw
        except Exception as exc:
            self.trace.log(self.scenario, "llm_error", latency_ms=round((time.perf_counter()-start)*1000),
                           error=repr(exc))
            raise


class TracedExtractor(ConverseRescueClient):
    def __init__(self, trace, scenario):
        super().__init__()
        self.trace, self.scenario = trace, scenario

    async def _generate(self, system, data, max_tokens):
        start = time.perf_counter()
        self.trace.log(self.scenario, "rescue_llm_prompt", system_prompt=system,
                       user_data=data, max_tokens=max_tokens, temperature=0.1)
        raw = await super()._generate(system, data, max_tokens)
        self.trace.log(self.scenario, "rescue_llm_raw_json",
                       latency_ms=round((time.perf_counter()-start)*1000), raw_output=raw)
        return raw


def orchestrator(trace, name):
    wrap = lambda label, obj: TracedProvider(label, obj, trace, name)
    return TripOrchestrator(tourism=wrap("tourism", TourismClient()),
        hotels=wrap("hotels", HotelClient()), buses=wrap("buses", BusClient()),
        trains=wrap("trains", TrainClient()), route=wrap("route", RouteClient()),
        flights=wrap("flights", FlightClient()))


CASES = [
    {"name": "happy_kochi", "message": "Kochi from Rajapalayam, 15 to 17 Dec, just me. Train 3AC, history and architecture please.",
     "draft": {"origin": "Rajapalayam", "destination": "Kochi", "start_date": "2026-12-15",
               "end_date": "2026-12-17", "travelers": 1, "budget_level": "medium",
               "transport_mode": "train", "berth_preference": "3A",
               "hotel_category": "any", "interests": ["history", "architecture"]},
     "rescue": "my train got delayed 6 hours"},
    {"name": "tight_coimbatore", "message": "Just a quick cheap Coimbatore trip from Chennai, 3rd to 4th. Sleeper train and an easy pace.",
     "draft": {"origin": "Chennai", "destination": "Coimbatore", "start_date": "2026-12-03",
               "end_date": "2026-12-04", "travelers": 1, "budget_level": "low",
               "transport_mode": "train", "berth_preference": "SL", "hotel_category": "budget",
               "pace": "relaxed", "interests": ["nature"]},
     "rescue": "it's pouring, what can we do instead?"},
    {"name": "vague_group", "message": "Maybe Coimbatore from Chennai around 10-12 Dec, temples please. We can go with a moderate pace.",
     "draft": {"origin": "Chennai", "destination": "Coimbatore", "start_date": "2026-12-10",
               "end_date": "2026-12-12", "budget_level": "medium", "transport_mode": "train",
               "berth_preference": "3A", "hotel_category": "any", "pace": "moderate",
               "interests": ["temples"]},
     "rescue": "we missed the museum slot, fix the rest of the day"},
    {"name": "flight_delay", "message": "Hyderabad from Chennai, 20-22 Dec. One adult, flight please; I like museums.",
     "draft": {"origin": "Chennai", "destination": "Hyderabad", "start_date": "2026-12-20",
               "end_date": "2026-12-22", "travelers": 1, "budget_level": "high",
               "transport_mode": "flight", "hotel_category": "any", "interests": ["museums"]},
     "rescue": "my flight got delayed 6 hours"},
]


def evaluate_plan(trip, itinerary, context, text):
    problems = []
    days = (trip.end_date - trip.start_date).days
    if len(itinerary.days) != days or itinerary.summary.days != days:
        problems.append(f"days expected {days}, got {len(itinerary.days)} / summary {itinerary.summary.days}")
    if itinerary.summary.travelers != trip.travelers:
        problems.append(f"travelers expected {trip.travelers}, got {itinerary.summary.travelers}")
    if itinerary.summary.pace != trip.preferences.activities.pace.value:
        problems.append(f"pace expected {trip.preferences.activities.pace.value}, got {itinerary.summary.pace}")
    requested_mode = trip.preferences.transport.mode.value
    for leg in ("outbound", "return"):
        choice = getattr(itinerary, f"{leg}_transport")
        if requested_mode != "any" and (choice is None or choice.mode != requested_mode):
            problems.append(f"{leg} mode expected {requested_mode}, got {choice.mode if choice else None}")
        if choice and choice.mode == "train":
            trains = getattr(context, f"{leg}_trains")
            if not any(t.train_number == choice.train_number for t in trains):
                problems.append(f"{leg} train {choice.train_number} absent from provider")
        if choice and choice.mode == "bus":
            buses = getattr(context, f"{leg}_buses")
            if not any(b.operator_name == choice.operator_name and (b.available_seats or 0) > 0 for b in buses):
                problems.append(f"{leg} bus absent or seats unverified")
        if choice and choice.mode == "flight":
            flights = getattr(context, f"{leg}_flights")
            if not any(f.flight_id == choice.flight_id for f in flights):
                problems.append(f"{leg} flight {choice.flight_id} absent from provider")
    hotel_ids = {h.id for h in context.hotels}
    if not itinerary.hotel or itinerary.hotel.hotel_id not in hotel_ids:
        problems.append("missing or unsourced hotel")
    else:
        ceiling = {"low": 1500, "medium": 5000, "high": float("inf")}[trip.preferences.budget.level.value]
        if itinerary.hotel.price_per_night is None:
            problems.append("hotel rate unverified")
        elif itinerary.hotel.price_per_night > ceiling:
            problems.append(f"hotel rate {itinerary.hotel.price_per_night} exceeds nightly target {ceiling}")
    known = {a.name.casefold() for a in context.attractions}
    seen = set()
    for day in itinerary.days:
        for activity in day.activities:
            key = activity.attraction_name.casefold()
            if key not in known:
                problems.append(f"unsourced attraction: {activity.attraction_name}")
            if key in seen:
                problems.append(f"duplicate attraction: {activity.attraction_name}")
            seen.add(key)
            arrival = itinerary.outbound_transport
            if arrival and arrival.arrival_date == day.date:
                arrival_at = clock_minutes(arrival.arrival_time)
                visit_at = clock_minutes(activity.start_time)
                if arrival_at is not None and visit_at is not None and visit_at < arrival_at:
                    problems.append(f"{activity.attraction_name} starts before arrival on {day.date}")
    interests = {interest.casefold() for interest in trip.preferences.activities.interests}
    names = " ".join(seen)
    if "museums" in interests and "museum" not in names:
        problems.append("museum preference not reflected in itinerary")
    if "temples" in interests and "temple" not in names:
        problems.append("temple preference not reflected in itinerary")
    if "nature" in interests and not any(word in names for word in ("lake", "garden", "park", "bird", "valankulam")):
        problems.append("nature preference not reflected in itinerary")
    if not itinerary.arrival_to_hotel or not itinerary.arrival_to_hotel.instruction:
        problems.append("no arrival-to-hotel instruction")
    chunks = whatsapp_messages.split_whatsapp_text(text)
    if not chunks or any(len(chunk) > 4096 or "```" in chunk for chunk in chunks):
        problems.append(f"WhatsApp formatting empty/long/broken (length {len(text)})")
    if "HOTEL & STAY" not in text or "DAY-BY-DAY ITINERARY" not in text:
        problems.append("missing WhatsApp sections")
    if itinerary.days and itinerary.days[0].activities and "https://www.google.com/maps/dir/" not in text:
        problems.append("missing sightseeing directions")
    return problems


def clock_minutes(value):
    if not value:
        return None
    for pattern in ("%I:%M %p", "%H:%M"):
        try:
            parsed = datetime.strptime(value.strip(), pattern)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            pass
    return None


def open_during(hours, day, start, duration):
    periods = (hours or {}).get("periods")
    if periods is None:
        return None
    if not periods:
        return False
    weekday = (date.fromisoformat(day).weekday() + 1) % 7  # Google: Sunday=0
    moment = weekday * 1440 + start
    for period in periods:
        opening = period.get("open") or {}
        closing = period.get("close")
        if not closing:
            return True  # Google 24-hour period
        start_week = opening.get("day", 0) * 1440 + opening.get("hour", 0) * 60 + opening.get("minute", 0)
        end_week = closing.get("day", 0) * 1440 + closing.get("hour", 0) * 60 + closing.get("minute", 0)
        if end_week <= start_week:
            end_week += 7 * 1440
        for shift in (-7 * 1440, 0, 7 * 1440):
            if start_week + shift <= moment and moment + duration <= end_week + shift:
                return True
    return False


async def audit_live_realism(trip, itinerary, context, trace, name):
    """Check routed travel gaps and Google Places regular hours with real APIs."""
    issues, warnings = [], []
    attractions = {a.name.casefold(): a for a in context.attractions}
    hotel = next((h for h in context.hotels if itinerary.hotel and h.id == itinerary.hotel.hotel_id), None)
    routes = HotelRoutesClient()
    async with httpx.AsyncClient(timeout=20) as client:
        hours_cache = {}
        for day in itinerary.days:
            activities = day.activities
            locations = [attractions.get(a.attraction_name.casefold()) for a in activities]
            if hotel and hotel.latitude is not None and hotel.longitude is not None and all(
                    a and a.latitude is not None and a.longitude is not None for a in locations):
                origins = [(hotel.latitude, hotel.longitude)] + [
                    (a.latitude, a.longitude) for a in locations[:-1]]
                destinations = [(a.latitude, a.longitude) for a in locations]
                matrix = await routes.matrix(origins, destinations)
                trace.log(name, "live_google_routes_day", day=day.date,
                          origins=origins, destinations=destinations, matrix=matrix)
                for index in range(1, len(activities)):
                    road = matrix.get((index, index))
                    prev = clock_minutes(activities[index-1].start_time)
                    current = clock_minutes(activities[index].start_time)
                    duration = activities[index-1].duration_minutes or 0
                    if road is None:
                        warnings.append(f"route unverified: {activities[index-1].attraction_name} to {activities[index].attraction_name}")
                    elif prev is not None and current is not None and prev + duration + road.minutes > current:
                        issues.append(f"insufficient travel gap on {day.date}: {activities[index-1].attraction_name} to {activities[index].attraction_name} needs {road.minutes} min drive")
            for activity in activities:
                start = clock_minutes(activity.start_time)
                if start is None or activity.attraction_name.casefold() not in attractions:
                    continue
                place = attractions[activity.attraction_name.casefold()]
                if activity.attraction_name not in hours_cache:
                    payload = {"textQuery": f"{activity.attraction_name}, {trip.destination}, India",
                               "maxResultCount": 1}
                    if place.latitude is not None and place.longitude is not None:
                        payload["locationBias"] = {"circle": {"center": {
                            "latitude": place.latitude, "longitude": place.longitude}, "radius": 1000}}
                    try:
                        response = await client.post("https://places.googleapis.com/v1/places:searchText",
                            json=payload, headers={"X-Goog-Api-Key": settings.google_maps_api_key,
                                "X-Goog-FieldMask": "places.id,places.displayName,places.regularOpeningHours,places.businessStatus"})
                        data = response.json() if response.is_success else {}
                        found = (data.get("places") or [{}])[0]
                        trace.log(name, "live_google_places_hours", query=payload,
                                  status=response.status_code, output=found)
                        hours_cache[activity.attraction_name] = found
                    except Exception as exc:
                        trace.log(name, "live_google_places_hours_error", place=activity.attraction_name,
                                  error=type(exc).__name__)
                        hours_cache[activity.attraction_name] = {}
                found = hours_cache[activity.attraction_name]
                matched_name = ((found.get("displayName") or {}).get("text") or "").casefold()
                if not matched_name or (activity.attraction_name.casefold() not in matched_name and
                                        matched_name not in activity.attraction_name.casefold()):
                    warnings.append(f"opening hours unverified: {activity.attraction_name} (place match)")
                    continue
                if found.get("businessStatus") in {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}:
                    issues.append(f"scheduled closed place: {activity.attraction_name}")
                    continue
                open_result = open_during(found.get("regularOpeningHours"), day.date,
                                          start, activity.duration_minutes or 60)
                if open_result is False:
                    issues.append(f"scheduled outside regular hours: {activity.attraction_name} on {day.date} at {activity.start_time}")
                elif open_result is None:
                    warnings.append(f"opening hours unverified: {activity.attraction_name}")
    return issues, warnings


async def hydrate_live_opening_hours(trip, itinerary, context, trace, name):
    """Use current Google Places records while the deployed tourism image is older."""
    selected = {a.attraction_name.casefold() for day in itinerary.days for a in day.activities}
    if "museums" in {interest.casefold() for interest in trip.preferences.activities.interests}:
        selected.update(a.name.casefold() for a in context.attractions if "museum" in a.name.casefold())
    async with httpx.AsyncClient(timeout=20) as client:
        for place in context.attractions:
            if place.name.casefold() not in selected or place.opening_hours is not None:
                continue
            payload = {"textQuery": f"{place.name}, {trip.destination}, India", "maxResultCount": 1}
            if place.latitude is not None and place.longitude is not None:
                payload["locationBias"] = {"circle": {"center": {
                    "latitude": place.latitude, "longitude": place.longitude}, "radius": 1000}}
            try:
                response = await client.post("https://places.googleapis.com/v1/places:searchText",
                    json=payload, headers={"X-Goog-Api-Key": settings.google_maps_api_key,
                        "X-Goog-FieldMask": "places.id,places.displayName,places.regularOpeningHours,places.businessStatus"})
                found = ((response.json().get("places") or [{}])[0] if response.is_success else {})
                match = ((found.get("displayName") or {}).get("text") or "").casefold()
                trace.log(name, "schedule_places_lookup", request=payload, status=response.status_code,
                          output=found)
                if match and (match in place.name.casefold() or place.name.casefold() in match):
                    place.place_id = found.get("id")
                    place.opening_hours = found.get("regularOpeningHours")
                    place.business_status = found.get("businessStatus")
            except (httpx.HTTPError, ValueError) as exc:
                trace.log(name, "schedule_places_error", place=place.name, error=type(exc).__name__)


async def run_case(case, trace, base):
    name = case["name"]
    start = time.perf_counter()
    draft = whatsapp_trip.TripDraft.model_validate(case["draft"])
    trip = TripRequest.model_validate(draft.to_trip_request().model_dump(mode="json"))
    trace.log(name, "whatsapp_input", text=case["message"], draft=draft,
              parsed_state="CONFIRM_TRIP", planner_request=trip)
    orch = orchestrator(trace, name)
    context = await orch.build_context(trip)
    before = {place.name for place in context.attractions}
    await InterestPlacesClient(lambda step, **data: trace.log(name, step, **data)).add_requested_places(context)
    trace.log(name, "requested_places_lookup", added=[place for place in context.attractions
              if place.name not in before])
    trace.log(name, "assembled_context", context=context)
    problems = []
    if not context.hotels:
        problems.append("provider returned no dated hotels")
    try:
        planning_llm = TracedBedrock(trace, name)
        try:
            itinerary = await PlanningAgent(planning_llm).plan(context)
        finally:
            await planning_llm._client.close()
        trace.log(name, "model_itinerary", itinerary=itinerary)
        itinerary.planning_notes = None
        itinerary = ItineraryValidator().normalize_days(itinerary, context)
        trace.log(name, "normalized_itinerary", itinerary=itinerary)
        await hydrate_live_opening_hours(trip, itinerary, context, trace, name)
        itinerary = await ScheduleVerifier(
            TracedProvider("schedule_google_routes", HotelRoutesClient(), trace, name)).apply(itinerary, context)
        trace.log(name, "verified_schedule", itinerary=itinerary)
        itinerary = await HotelRecommendationService(
            TracedProvider("google_routes", HotelRoutesClient(), trace, name)).apply(itinerary, context)
        itinerary = ItineraryValidator().validate_and_calculate_costs(itinerary, context)
        data = itinerary.model_dump(mode="json")
        text = whatsapp_messages.format_itinerary_message(data, trip.origin, trip.destination,
            {"transport_mode": trip.preferences.transport.mode.value})
        trace.log(name, "whatsapp_final", itinerary=data, text=text,
                  latency_ms=round((time.perf_counter()-start)*1000))
        problems += evaluate_plan(trip, itinerary, context, text)
        realism_issues, realism_warnings = await audit_live_realism(trip, itinerary, context, trace, name)
        problems += realism_issues
        trace.log(name, "realism_audit", issues=realism_issues, warnings=realism_warnings)
    except Exception as exc:
        trace.log(name, "plan_error", error=repr(exc),
                  latency_ms=round((time.perf_counter()-start)*1000))
        return {"scenario": name, "plan": "FAIL", "rescue": "NOT RUN", "issues": [repr(exc)]}

    # Each case uses a real saved-trip context, and a casual traveler disruption.
    message = case["rescue"]
    extraction_request = RescueExtractionRequest(trip=trip, itinerary=data,
        history=[{"role": "user", "text": message}], message=message)
    trace.log(name, "rescue_input", message=message, trip=trip, itinerary=data,
              parsed_state="RESCUE_WAITING_DETAILS")
    rescue_start = time.perf_counter()
    try:
        extracted = await TracedExtractor(trace, name).extract(extraction_request)
        trace.log(name, "rescue_extracted", fields=extracted)
        rescue_problems = []
        if "train got delayed" in message and extracted.affected_item != "train":
            rescue_problems.append(f"train delay extracted as {extracted.affected_item}")
        if "flight got delayed" in message and extracted.affected_item != "flight":
            rescue_problems.append(f"flight delay extracted as {extracted.affected_item}")
        request = RecoveryRequest(trip=trip, itinerary=data, change=message,
            rescue_history=[{"role": "user", "text": message}],
            extracted_fields=extracted.model_dump())
        recovery_llm = TracedBedrock(trace, name)
        try:
            result = await RecoveryService(orch, recovery_llm).recover(request)
        finally:
            await recovery_llm._client.close()
        trace.log(name, "rescue_final", result=result,
                  latency_ms=round((time.perf_counter()-rescue_start)*1000))
        if result.status == "needs_clarification":
            if not result.clarification:
                rescue_problems.append("clarification has no question")
        elif result.status == "ready":
            if not result.options or any(o.evidence is None for o in result.options):
                rescue_problems.append("rescue option lacks provider evidence")
        elif result.status != "no_verified_options":
            rescue_problems.append("invalid rescue status")
        if message.startswith("we missed the museum") and result.change_kind not in ("place_delay", "closure"):
            rescue_problems.append(f"museum disruption misrouted as {result.change_kind}")
        if "pouring" in message and result.change_kind == "unknown":
            rescue_problems.append("rain disruption not understood")
        if "pouring" in message and any(o.category != "experience" for o in result.options):
            rescue_problems.append("rain rescue suggested transport or outdoor options")
        problems += rescue_problems
        rescue_status = "PASS" if not rescue_problems else "FAIL"
    except Exception as exc:
        trace.log(name, "rescue_error", error=repr(exc),
                  latency_ms=round((time.perf_counter()-rescue_start)*1000))
        rescue_status = "FAIL"
        problems.append("rescue: " + repr(exc))
    return {"scenario": name, "plan": "PASS" if not (evaluate_plan(trip, itinerary, context, text) or realism_issues) else "FAIL",
            "rescue": rescue_status, "issues": problems, "warnings": realism_warnings}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://dreamdestiny.duckdns.org")
    parser.add_argument("--output", default=str(ROOT / ".e2e-trip-runs"))
    parser.add_argument("--scenario", choices=[case["name"] for case in CASES])
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    trace = Trace(output / "trace.jsonl")
    base = args.base.rstrip("/")
    for attr in ("tourism_service_url", "transport_bus_service_url",
                 "transport_train_service_url", "transport_flight_service_url",
                 "flight_service_url", "hotel_service_url", "route_service_url"):
        setattr(settings, attr, base)
    settings.http_timeout = 35
    if not settings.bedrock_api_key:
        raise SystemExit("BEDROCK_API_KEY is needed in the local .env for full prompt tracing")
    results = []
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            health = await client.get(base + "/health")
            trace.log("all", "deployed_health", status=health.status_code, body=health.text)
        for case in CASES:
            if args.scenario and case["name"] != args.scenario:
                continue
            print("Running", case["name"], flush=True)
            results.append(await run_case(case, trace, base))
            print(results[-1], flush=True)
    finally:
        trace.close()
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Trace:", output / "trace.jsonl")
    return 0 if all(row["plan"] == "PASS" and row["rescue"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
