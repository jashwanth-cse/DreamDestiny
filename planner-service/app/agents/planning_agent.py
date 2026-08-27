"""
PlanningAgent — the AI decision-maker for trip itineraries.

Responsibilities:
  - Accept ONLY a TripContext.
  - Build a minimal, grounded JSON representation of the context for the LLM.
  - Send system prompt + context to GeminiClient.
  - Validate the model response with Pydantic Itinerary schema.
  - Return a typed Itinerary object.
  - NEVER import or call service clients (Tourism, Hotel, Transport, Route).
  - NEVER calculate distances, costs, or durations.
  - NEVER repair invalid LLM responses with invented data.

Architecture note:
  The agent depends on GeminiClient (injected), not on the SDK directly,
  so the LLM backend can be swapped by changing the constructor only.
"""

import json
import logging
from datetime import timedelta

from pydantic import ValidationError

from app.agents.base import BaseAgent, AgentError
from app.schemas.context import TripContext
from app.schemas.itinerary import Itinerary
from app.services.llm.gemini_client import GeminiClient, GeminiError
from app.services.llm.prompts import PLANNING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_context_payload(context: TripContext) -> dict:
    """
    Produce a minimal, grounded JSON representation of TripContext.

    Only fields the LLM needs to make decisions are included.
    Verbose fields (metadata, pagination counts) are omitted to keep
    the prompt token count low and focus the model on decision data.
    """
    trip = context.trip
    prefs = trip.preferences

    # Compute trip days for the summary
    trip_days = (trip.end_date - trip.start_date).days

    return {
        "trip": {
            "origin": trip.origin,
            "destination": trip.destination,
            "start_date": trip.start_date.isoformat(),
            "end_date": trip.end_date.isoformat(),
            "days": trip_days,
            "travelers": trip.travelers,
            "preferences": {
                "budget": prefs.budget.level.value,
                "transport_mode": prefs.transport.mode.value,
                "hotel_category": prefs.hotel.category.value,
                "pace": prefs.activities.pace.value,
                "interests": prefs.activities.interests,
                "family_friendly": prefs.activities.family_friendly,
                "food": (
                    {
                        "dietary_restrictions": prefs.food.dietary_restrictions.value,
                        "cuisines": prefs.food.cuisines,
                    }
                    if prefs.food else None
                ),
            },
        },
        "attractions": [
            {
                "name": a.name,
                "address": a.address,
                "rating": a.rating,
                "review_count": a.review_count,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "types": a.types,
            }
            for a in context.attractions
        ],
        "hotels": [
            {
                "id": h.id,
                "name": h.name,
                "rating": h.rating,
                "hotel_class": h.hotel_class,
                "price_per_night": h.price.per_night,
                "price_total": h.price.total,
                "currency": h.price.currency,
                "amenities": h.amenities,
            }
            for h in context.hotels
        ],
        "outbound_trains": [
            {
                "train_number": t.train_number,
                "train_name": t.train_name,
                "departure_time": t.departure_time,
                "arrival_time": t.arrival_time,
                "duration": t.duration,
                "lowest_fare": t.lowest_fare,
                "rating": t.rating,
                "has_pantry": t.has_pantry,
                "running_days": t.running_days,
            }
            for t in context.outbound_trains
        ],
        "outbound_buses": [
            {
                "operator_name": b.operator_name,
                "bus_type": b.bus_type,
                "departure_time": b.departure_time,
                "arrival_time": b.arrival_time,
                "duration": b.duration,
                "minimum_fare": b.minimum_fare,
                "rating": b.rating,
            }
            for b in context.outbound_buses
        ],
        "return_trains": [
            {
                "train_number": t.train_number,
                "train_name": t.train_name,
                "departure_time": t.departure_time,
                "arrival_time": t.arrival_time,
                "duration": t.duration,
                "lowest_fare": t.lowest_fare,
                "rating": t.rating,
                "running_days": t.running_days,
            }
            for t in context.return_trains
        ],
        "return_buses": [
            {
                "operator_name": b.operator_name,
                "bus_type": b.bus_type,
                "departure_time": b.departure_time,
                "arrival_time": b.arrival_time,
                "duration": b.duration,
                "minimum_fare": b.minimum_fare,
                "rating": b.rating,
            }
            for b in context.return_buses
        ],
        "route": (
            {
                "distance_km": context.route.distance_km,
                "modes": [
                    {"mode": r.mode, "duration_minutes": r.duration_minutes}
                    for r in context.route.routes
                ],
            }
            if context.route else None
        ),
    }


def _itinerary_json_schema() -> dict:
    """
    Return the JSON schema for Itinerary so Gemini can constrain its output.
    Uses Pydantic's schema generation.
    """
    return Itinerary.model_json_schema()


class PlanningAgent(BaseAgent[Itinerary]):
    """
    Uses Gemini to produce a grounded, structured Itinerary from TripContext.

    Constructor-injected with a GeminiClient so the LLM backend is swappable
    and the agent remains independently testable.
    """

    def __init__(self, llm: GeminiClient) -> None:
        self._llm = llm

    async def plan(self, context: TripContext) -> Itinerary:
        """
        Produce an Itinerary for the given TripContext.

        Flow:
          1. Serialize TripContext into a minimal, grounded payload dict.
          2. Send system prompt + payload to GeminiClient.
          3. Validate the raw JSON response with Pydantic.
          4. Return a typed Itinerary.

        Raises:
            AgentError: On LLM failure or schema validation failure.
        """
        payload = _build_context_payload(context)
        schema = _itinerary_json_schema()

        logger.info(
            "PlanningAgent.plan: %s → %s | %d attractions | %d hotels | "
            "%d outbound trains | %d outbound buses",
            context.trip.origin,
            context.trip.destination,
            len(context.attractions),
            len(context.hotels),
            len(context.outbound_trains),
            len(context.outbound_buses),
        )

        # ── Call LLM ─────────────────────────────────────────────────────────
        try:
            raw = await self._llm.generate_json(
                system_prompt=PLANNING_SYSTEM_PROMPT,
                user_data=payload,
                json_schema=schema,
            )
        except GeminiError as exc:
            raise AgentError(str(exc), cause=exc)

        # ── Validate with Pydantic ────────────────────────────────────────────
        # If the model returns invalid structured data, we fail safely.
        # We never attempt to repair invented or missing factual values.
        try:
            itinerary = Itinerary.model_validate(raw)
        except ValidationError as exc:
            logger.error(
                "PlanningAgent: Itinerary schema validation failed.\n"
                "Raw response: %s\nErrors: %s",
                json.dumps(raw, indent=2)[:1000],
                exc,
            )
            raise AgentError(
                "The planning model returned a response that did not match "
                "the expected Itinerary structure. Please try again.",
                cause=exc,
            )

        logger.info(
            "PlanningAgent.plan complete: %d days planned, hotel=%s",
            len(itinerary.days),
            itinerary.hotel.hotel_id if itinerary.hotel else "none",
        )
        return itinerary
