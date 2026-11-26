"""Independent specialist agents with bounded read-only tool calls.

Each specialist retrieves a different slice of provider context, reasons about it
with the configured model, and returns only IDs from that slice. Model output never
becomes a factual price, schedule, or availability claim.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import re

from app.recovery.models import AgentTrace, Evidence, RecoveryOption
from app.schemas.context import TripContext


def _evidence(provider: str, fetched_at: datetime, minutes: int, status: str) -> Evidence:
    return Evidence(provider=provider, fetched_at=fetched_at,
                    valid_until=fetched_at + timedelta(minutes=minutes), source_status=status)


class ContextTools:
    """Typed, read-only tool boundary. One call per specialist per run."""

    def __init__(self, context: TripContext, fetched_at: datetime, direction: str = "outbound"):
        self.context = context
        self.fetched_at = fetched_at
        self.direction = direction

    def mobility_options(self) -> list[RecoveryOption]:
        found: list[RecoveryOption] = []
        for direction in (self.direction,):
            for train in getattr(self.context, f"{direction}_trains")[:12]:
                selected = next((c for c in train.classes if c.bookable and c.fare > 0), None)
                if not selected:
                    continue
                found.append(RecoveryOption(
                    id=f"{direction}:train:{train.train_number}:{selected.travel_class}",
                    category="mobility", title=f"{train.train_name} ({train.train_number}) {selected.travel_class}",
                    reason=f"{direction.title()} train option", price=selected.fare,
                    departure_time=train.departure_time, arrival_time=train.arrival_time,
                    source_id=train.train_number, evidence=_evidence("train-service", self.fetched_at, 10, "search_result"),
                    warnings=["RAC is not a confirmed berth"] if selected.availability.upper().startswith("RAC") else [],
                ))
            for i, bus in enumerate(getattr(self.context, f"{direction}_buses")[:12]):
                if bus.minimum_fare is None or bus.minimum_fare <= 0 or bus.available_seats == 0:
                    continue
                found.append(RecoveryOption(
                    id=f"{direction}:bus:{i}", category="mobility",
                    title=f"{bus.operator_name or 'Bus'} {bus.bus_type or ''}".strip(),
                    reason=f"{direction.title()} bus option", price=bus.minimum_fare,
                    departure_time=bus.departure_time, arrival_time=bus.arrival_time,
                    source_id=f"bus:{i}", evidence=_evidence("bus-service", self.fetched_at, 10, "search_result"),
                ))
            for flight in getattr(self.context, f"{direction}_flights")[:12]:
                if flight.price is None or flight.price <= 0:
                    continue
                found.append(RecoveryOption(
                    id=f"{direction}:flight:{flight.flight_id}", category="mobility",
                    title=f"{flight.airline or 'Flight'} {flight.flight_number or ''}".strip(),
                    reason=f"{direction.title()} flight option", price=flight.price, currency=flight.currency,
                    departure_time=flight.departure_time, arrival_time=flight.arrival_time,
                    source_id=flight.flight_id, evidence=_evidence("flight-service", self.fetched_at, 10, "search_result"),
                ))
        return found

    def experience_options(self) -> list[RecoveryOption]:
        found: list[RecoveryOption] = []
        for i, place in enumerate(self.context.attractions[:20]):
            found.append(RecoveryOption(
                id=f"activity:{i}", category="experience", title=place.name,
                reason="Alternate activity to consider", source_id=place.name,
                evidence=_evidence("tourism-service", self.fetched_at, 60, "schedule"),
                warnings=["Opening hours and entry fees have not been verified"],
            ))
        return found


async def _select_ids(llm, instruction: str, candidates: list[RecoveryOption], change: str,
                      rescue_context: dict | None = None) -> list[str]:
    if not candidates:
        return []
    # Hard limit: bounded model input, one model call, maximum three selections.
    brief = [{"id": x.id, "title": x.title, "price": x.price,
              "departure_time": x.departure_time, "warnings": x.warnings} for x in candidates[:30]]
    try:
        raw = await asyncio.wait_for(llm.generate_json(
            system_prompt=instruction + " Select up to 3 candidate IDs. Never invent an ID. Return JSON only.",
            user_data={"change": change, "candidates": brief, **(rescue_context or {})},
            json_schema={"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}, "required": ["ids"]},
        ), timeout=35)
        ids = raw.get("ids", [])
        allowed = {x.id for x in candidates}
        return list(dict.fromkeys(x for x in ids if isinstance(x, str) and x in allowed))[:3]
    except Exception:
        # A specialist can still return factual provider options when the model is down.
        return [x.id for x in candidates[:3]]


class MobilityAgent:
    name = "mobility"

    def __init__(self, llm):
        self.llm = llm

    async def run(self, tools: ContextTools, change: str, rescue_context: dict | None = None):
        candidates = tools.mobility_options()
        ids = await _select_ids(self.llm, "You are a mobility recovery agent. Prefer affordable, available transport that fits the reported disruption.", candidates, change, rescue_context)
        lookup = {x.id: x for x in candidates}
        return [lookup[x] for x in ids], AgentTrace(agent=self.name, tools=["mobility_options"], considered=len(candidates), selected=ids)


class ExperienceAgent:
    name = "experience"

    def __init__(self, llm):
        self.llm = llm

    async def run(self, tools: ContextTools, change: str, rescue_context: dict | None = None):
        candidates = tools.experience_options()
        # A closed venue must never be returned as its own replacement.
        candidates = [x for x in candidates if x.title.casefold() not in change.casefold()]
        ids = await _select_ids(self.llm, "You are a local experience recovery agent. Suggest relevant nearby activities, never the closed venue itself.", candidates, change, rescue_context)
        lookup = {x.id: x for x in candidates}
        return [lookup[x] for x in ids], AgentTrace(agent=self.name, tools=["experience_options"], considered=len(candidates), selected=ids)


class NearbyStayAgent:
    name = "nearby_stay"

    def __init__(self, llm):
        self.llm = llm

    async def run(self, candidates: list[RecoveryOption], change: str, rescue_context: dict | None = None):
        ids = await _select_ids(self.llm,
            "You are a local lodging agent. Select nearby hotels that fit an arrived traveler. "
            "Google Places is location data, not room inventory; never claim availability or price.",
            candidates[:6], change, rescue_context)
        lookup = {x.id: x for x in candidates}
        selected = [lookup[x] for x in ids]
        selected.sort(key=lambda x: (x.travel_minutes or 9999, x.distance_km or 9999))
        return selected, AgentTrace(agent=self.name, tools=["google_places_hotels", "routes_matrix"],
                                    considered=len(candidates), selected=ids)


class NearbyExperienceAgent:
    name = "nearby_experience"

    def __init__(self, llm):
        self.llm = llm

    async def run(self, candidates: list[RecoveryOption], change: str, rescue_context: dict | None = None):
        ids = await _select_ids(self.llm,
            "You are a local sightseeing agent. Select nearby places for a late arrival. "
            "Do not claim that a venue is open or that tickets are available.",
            candidates[:8], change, rescue_context)
        lookup = {x.id: x for x in candidates}
        selected = [lookup[x] for x in ids]
        selected.sort(key=lambda x: (x.travel_minutes or 9999, x.distance_km or 9999))
        return selected, AgentTrace(agent=self.name, tools=["google_places_attractions", "routes_matrix"],
                                    considered=len(candidates), selected=ids)


def classify_change(change: str) -> str:
    text = change.casefold()
    # Arrival has already happened: a replacement outbound ticket is irrelevant.
    if (re.search(r"\b(arriv(?:e|ed)|reach(?:ed)?|got to|made it to)\b", text)
            and re.search(r"\b(delayed|delay|late|stuck)\b", text)):
        return "arrival_delay"
    if re.search(r"\b(cancelled|canceled|cancel|missed)\b", text):
        return "cancellation"
    if re.search(r"\b(delayed|delay|late|stuck)\b", text):
        return "delay"
    if re.search(r"\b(closed|closure|shut|unavailable)\b", text):
        return "closure"
    if re.search(r"\b(cheaper|budget|walking|pace|change|prefer)\b", text):
        return "preference"
    return "unknown"
