from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

from app.recovery.agents import (ContextTools, ExperienceAgent, MobilityAgent,
                                 NearbyExperienceAgent, NearbyStayAgent, classify_change)
from app.recovery.models import (Evidence, RecoveryLocation, RecoveryRequest,
                                 RecoveryResult, RecoveryOption)
from app.recovery.nearby import NearbyProvider, NearbySearchError
from app.recovery.interpreter import compact_trip


class RecoveryService:
    def __init__(self, orchestrator, llm, now=None, nearby=None):
        self.orchestrator = orchestrator
        self.mobility = MobilityAgent(llm)
        self.experience = ExperienceAgent(llm)
        self.nearby_stay = NearbyStayAgent(llm)
        self.nearby_experience = NearbyExperienceAgent(llm)
        self.nearby = nearby or NearbyProvider()
        self.now = now or (lambda: datetime.now(timezone.utc))

    async def recover(self, request: RecoveryRequest) -> RecoveryResult:
        fields = request.extracted_fields
        disruption = fields.get("disruption_type")
        affected_item = fields.get("affected_item")
        if affected_item == "place" and disruption in {"delayed", "missed"}:
            kind = "place_delay"
        elif disruption in {"missed", "cancelled"}:
            kind = "cancellation"
        elif disruption == "delayed":
            kind = "delay"
        elif disruption == "closed":
            kind = "closure"
        elif disruption == "preference_change":
            kind = "preference"
        else:
            kind = classify_change(request.change)
        if kind == "unknown":
            return RecoveryResult(status="needs_clarification", change_kind="unknown",
                                  clarification="What changed: a delay, cancellation, closure, or preference? Include the affected booking or place.")
        local_today = self.now().astimezone(ZoneInfo("Asia/Kolkata")).date()
        if request.trip.end_date < local_today:
            return RecoveryResult(status="needs_clarification", change_kind=kind,
                                  clarification="This saved trip has ended. Please start a new trip for new travel dates.")
        if kind == "arrival_delay":
            return await self._recover_arrival(request)
        if kind == "place_delay":
            return await self._recover_place_delay(request)
        matched = [c for c in request.commitments if c.title.casefold() in request.change.casefold()]
        if not matched and kind in {"delay", "cancellation"}:
            transports = sorted((c for c in request.commitments if c.kind == "transport" and c.starts_at),
                                key=lambda c: c.starts_at)
            if len(transports) == 1:
                matched = transports
        affected = [c.id for c in matched]
        if kind in {"delay", "cancellation"} and matched:
            delay_match = re.search(r"(\d+)\s*(hour|hr|minute|min)", request.change.casefold())
            delay_minutes = (int(delay_match.group(1)) * (60 if delay_match.group(2) in {"hour", "hr"} else 1)
                             if delay_match else 60)
            for source in matched:
                if source.ends_at:
                    threshold = source.ends_at + timedelta(minutes=delay_minutes + 30)
                    affected.extend(c.id for c in request.commitments
                                    if c.id != source.id and c.starts_at and source.ends_at <= c.starts_at < threshold)
        affected = list(dict.fromkeys(affected))
        lookup_trip = request.trip
        if request.trip.start_date < local_today:
            lookup_trip = request.trip.model_copy(update={
                "start_date": local_today,
                "end_date": max(request.trip.end_date, local_today + timedelta(days=1)),
            })
        context = await self.orchestrator.build_context(lookup_trip)
        fetched_at = self.now()
        direction = ("return" if affected_item == "return_bus" or
                     re.search(r"\b(return|back home|homebound)\b", request.change.casefold()) else "outbound")
        tools = ContextTools(context, fetched_at, direction)
        rescue_context = self._model_context(request)
        # Independent specialists execute concurrently; the supervisor combines only
        # their grounded outputs after deterministic validation.
        mobility_result, experience_result = await asyncio.gather(
            self.mobility.run(tools, request.change, rescue_context),
            self.experience.run(tools, request.change, rescue_context),
        )

        mobility, mobility_trace = mobility_result
        experience, experience_trace = experience_result
        rainy = bool(re.search(r"\b(rain|raining|pouring|storm|downpour)\b", request.change.casefold()))
        if rainy:
            indoor_types = {"museum", "art_gallery", "aquarium", "shopping_mall", "movie_theater", "library"}
            indoor_names = {a.name.casefold() for a in context.attractions
                            if indoor_types.intersection(a.types)}
            booked_names = {c.title.casefold() for c in request.commitments
                            if c.kind == "activity" and c.confirmed}
            pool = [option for option in tools.experience_options()
                    if option.title.casefold() in indoor_names and
                    option.title.casefold() not in booked_names]
            for option in pool:
                option.reason = "Indoor alternative during rain; verify opening hours before visiting"
        else:
            pool = (experience if kind == "closure" else mobility + experience)
        valid: list[RecoveryOption] = []
        for option in pool:
            if not option.evidence or option.evidence.valid_until <= self.now():
                continue
            if option.price is not None and option.price < 0:
                continue
            if option.currency != "INR":
                option.warnings.append("Price currency differs from trip currency")
            if option.category == "experience" and kind != "closure":
                option.warnings.append("Check timing against the changed transport leg")
            valid.append(option)
        valid.sort(key=lambda x: (bool(x.warnings), x.price is None, x.price if x.price is not None else float("inf")))
        chosen = valid[:3]
        return RecoveryResult(
            status="ready" if chosen else "no_verified_options", change_kind=kind,
            affected_commitment_ids=affected, options=chosen,
            traces=[mobility_trace, experience_trace],
            expires_at=min((o.evidence.valid_until for o in chosen), default=None),
        )

    @staticmethod
    def _model_context(request: RecoveryRequest) -> dict:
        return {"trip": compact_trip(request.trip, request.itinerary),
                "history_summary": request.rescue_history_summary,
                "history": request.rescue_history[-10:],
                "extracted_fields": request.extracted_fields}

    async def _recover_place_delay(self, request: RecoveryRequest) -> RecoveryResult:
        if request.current_location is None:
            return RecoveryResult(status="needs_clarification", change_kind="place_delay",
                clarification="Where are you now? Share a WhatsApp location pin or a precise nearby landmark so I can adjust sightseeing around you.")
        try:
            location, _hotels, sights = await self.nearby.search(
                request.current_location, request.trip.destination)
        except NearbySearchError as exc:
            return RecoveryResult(status="needs_clarification", change_kind="place_delay",
                                  clarification=str(exc))
        now = self.now()
        reported = (request.current_location.address or "").split(",")[0].casefold()
        options = [RecoveryOption(
            id=f"nearby:activity:{p['id']}", category="experience", title=p["name"],
            reason=f"{p['travel_minutes']} min drive from your current landmark",
            source_id=p["id"], travel_minutes=p["travel_minutes"],
            distance_km=p["distance_km"], maps_url=p["maps_url"],
            evidence=Evidence(provider="Google Places and Routes", fetched_at=now,
                valid_until=now + timedelta(minutes=15), source_status="search_result"),
            warnings=["Opening hours, entry tickets and travel time may change"],
        ) for p in sights if p["name"].casefold() != reported and p["travel_minutes"] <= 45][:3]
        return RecoveryResult(
            status="ready" if options else "no_verified_options", change_kind="place_delay",
            options=options,
            location=RecoveryLocation(latitude=location.latitude, longitude=location.longitude,
                                      address=request.current_location.address or location.address),
            clarification=None if options else "I could not verify nearby sightseeing alternatives. Your itinerary is unchanged.",
            expires_at=min((o.evidence.valid_until for o in options), default=None),
        )

    async def _recover_arrival(self, request: RecoveryRequest) -> RecoveryResult:
        if request.current_location is None:
            return RecoveryResult(status="needs_clarification", change_kind="arrival_delay",
                clarification="You have already arrived. Please share your current WhatsApp location pin or a nearby landmark so I can find a nearby stay and sightseeing.")
        try:
            location, hotels, sights = await self.nearby.search(
                request.current_location, request.trip.destination)
        except NearbySearchError as exc:
            return RecoveryResult(status="needs_clarification", change_kind="arrival_delay",
                                  clarification=str(exc))

        fetched_at = self.now()
        evidence = lambda: Evidence(provider="Google Places and Routes", fetched_at=fetched_at,
                                    valid_until=fetched_at + timedelta(minutes=15),
                                    source_status="search_result")
        hotel_options = [RecoveryOption(
            id=f"nearby:hotel:{p['id']}", category="nearby_stay", title=p["name"],
            reason=f"{p['travel_minutes']} min drive from your shared location",
            source_id=p["id"], evidence=evidence(), distance_km=p["distance_km"],
            travel_minutes=p["travel_minutes"], maps_url=p["maps_url"],
            warnings=["Room availability, check-in and price are not verified"],
        ) for p in hotels[:6]]
        sight_options = [RecoveryOption(
            id=f"nearby:activity:{p['id']}", category="experience", title=p["name"],
            reason=f"{p['travel_minutes']} min drive from your shared location",
            source_id=p["id"], evidence=evidence(), distance_km=p["distance_km"],
            travel_minutes=p["travel_minutes"], maps_url=p["maps_url"],
            warnings=["Opening hours and entry fees are not verified"],
        ) for p in sights[:8]]
        (selected_hotels, hotel_trace), (selected_sights, sight_trace) = await asyncio.gather(
            self.nearby_stay.run(hotel_options, request.change, self._model_context(request)),
            self.nearby_experience.run(sight_options, request.change, self._model_context(request)),
        )
        if hotel_options:
            # The closest routed stay is always present even if model ranking omits it.
            selected_hotels = [hotel_options[0]] + [
                p for p in selected_hotels if p.id != hotel_options[0].id]
        nearby_activities = [{"id": p.source_id, "name": p.title,
                              "travel_minutes": p.travel_minutes, "maps_url": p.maps_url}
                             for p in selected_sights[:2]]
        for hotel in selected_hotels:
            hotel.nearby_activities = nearby_activities
        # Never offer a replacement outbound bus after the traveler reports arrival.
        chosen = selected_hotels[:3] or selected_sights[:3]
        return RecoveryResult(
            status="ready" if chosen else "no_verified_options", change_kind="arrival_delay",
            options=chosen, traces=[hotel_trace, sight_trace],
            location=RecoveryLocation(latitude=location.latitude, longitude=location.longitude,
                                      address=location.address),
            expires_at=fetched_at + timedelta(minutes=15) if chosen else None,
            disclaimer="Nearby Places are not room or ticket inventory. Confirm availability, hours and price directly.",
        )
