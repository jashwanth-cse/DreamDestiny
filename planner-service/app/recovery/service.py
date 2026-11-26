from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

from app.recovery.agents import ContextTools, ExperienceAgent, MobilityAgent, classify_change
from app.recovery.models import RecoveryRequest, RecoveryResult, RecoveryOption


class RecoveryService:
    def __init__(self, orchestrator, llm, now=None):
        self.orchestrator = orchestrator
        self.mobility = MobilityAgent(llm)
        self.experience = ExperienceAgent(llm)
        self.now = now or (lambda: datetime.now(timezone.utc))

    async def recover(self, request: RecoveryRequest) -> RecoveryResult:
        kind = classify_change(request.change)
        if kind == "unknown":
            return RecoveryResult(status="needs_clarification", change_kind="unknown",
                                  clarification="What changed: a delay, cancellation, closure, or preference? Include the affected booking or place.")
        local_today = self.now().astimezone(ZoneInfo("Asia/Kolkata")).date()
        if request.trip.end_date < local_today:
            return RecoveryResult(status="needs_clarification", change_kind=kind,
                                  clarification="This saved trip has ended. Please start a new trip for new travel dates.")
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
        direction = "return" if re.search(r"\b(return|back home|homebound)\b", request.change.casefold()) else "outbound"
        tools = ContextTools(context, fetched_at, direction)
        # Independent specialists execute concurrently; the supervisor combines only
        # their grounded outputs after deterministic validation.
        mobility_result, experience_result = await asyncio.gather(
            self.mobility.run(tools, request.change),
            self.experience.run(tools, request.change),
        )
        mobility, mobility_trace = mobility_result
        experience, experience_trace = experience_result
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
