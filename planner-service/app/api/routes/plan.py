"""
POST /plan

Full planning flow:
  TripRequest → TripOrchestrator → TripContext → PlanningAgent → Itinerary

This route is a thin adapter only. All intelligence lives in:
  - TripOrchestrator  (data assembly)
  - PlanningAgent     (LLM decision-making)
"""

import logging

from fastapi import APIRouter, HTTPException

from app.agents.base import AgentError
from app.agents.planning_agent import PlanningAgent
from app.business.itinerary_validator import ItineraryValidator
from app.clients.flight_client import FlightClient
from app.clients.hotel_client import HotelClient
from app.clients.route_client import RouteClient
from app.clients.tourism_client import TourismClient
from app.clients.transport_client import BusClient, TrainClient
from app.orchestration.trip_orchestrator import TripOrchestrator
from app.schemas.itinerary import Itinerary
from app.schemas.request import TripRequest
from app.schemas.request import TransportPref
from app.services.llm.llm_client import BedrockLLMClient
from app.services.hotel_recommendation import HotelRecommendationService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Singletons ────────────────────────────────────────────────────────────────
# Orchestrator is shared (has granular in-memory cache).
# BedrockLLMClient + PlanningAgent are lazy — initialised on first request so the
# server starts even if BEDROCK_API_KEY is not yet set.

_orchestrator = TripOrchestrator(
    tourism=TourismClient(),
    hotels=HotelClient(),
    buses=BusClient(),
    trains=TrainClient(),
    route=RouteClient(),
    flights=FlightClient(),
)

_validator = ItineraryValidator()
_hotel_recommendation = HotelRecommendationService()
_agent: PlanningAgent | None = None


def _get_agent() -> PlanningAgent:
    global _agent
    if _agent is None:
        try:
            _agent = PlanningAgent(llm=BedrockLLMClient())
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Planning agent is not configured (BEDROCK_API_KEY missing).",
            ) from exc
    return _agent


# ── Response model ────────────────────────────────────────────────────────────

class PlanResponse(Itinerary):
    """Thin alias — allows adding envelope fields later without breaking schema."""
    pass


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/plan",
    response_model=PlanResponse,
    summary="Generate a complete AI trip itinerary",
    description=(
        "Runs the full planning pipeline:\n\n"
        "1. Validates `TripRequest`.\n"
        "2. Collects data from all services concurrently (with caching).\n"
        "3. Passes the normalized `TripContext` to the Bedrock Planning Agent.\n"
        "4. Validates the structured itinerary response with Pydantic.\n"
        "5. Returns the typed `Itinerary`.\n\n"
        "**Strict grounding:** the agent references only data present in the "
        "TripContext. It never invents attractions, hotels, prices, or distances.\n\n"
        "**No LLM logic in the orchestrator.** "
        "**No service client calls in the agent.**"
    ),
    responses={
        400: {"description": "Invalid TripRequest"},
        503: {"description": "LLM unavailable or timed out"},
        500: {"description": "Planning failure"},
    },
)
async def plan(trip: TripRequest) -> PlanResponse:
    """
    Generate a day-by-day itinerary for the given TripRequest.
    """
    # ── Step 1: Orchestrate data ──────────────────────────────────────────
    try:
        context = await _orchestrator.build_context(trip)
    except Exception as exc:
        logger.exception("Orchestration failure during /plan: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to assemble trip data. Please try again.",
        )

    if trip.preferences.transport.mode == TransportPref.bus:
        missing = [leg for leg, options in (("outbound", context.outbound_buses),
                                           ("return", context.return_buses))
                   if not any((bus.available_seats or 0) > 0 for bus in options)]
        if missing:
            raise HTTPException(status_code=409,
                detail=f"No verified bus seats for the {', '.join(missing)} leg. Choose another transport mode or date.")
    if not context.hotels:
        raise HTTPException(status_code=503,
            detail="Dated hotel prices are unavailable right now. Please retry this trip shortly.")

    # ── Step 2: Run planning agent ────────────────────────────────────────
    try:
        itinerary = await _get_agent().plan(context)
    except HTTPException:
        raise  # 503 from _get_agent (missing key) — pass through cleanly
    except AgentError as exc:
        logger.error("PlanningAgent error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected planning failure: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during planning.",
        )

    if trip.preferences.transport.mode == TransportPref.bus:
        for leg, decision, options in (("outbound", itinerary.outbound_transport, context.outbound_buses),
                                       ("return", itinerary.return_transport, context.return_buses)):
            if (decision is None or decision.mode != "bus" or
                    not any(bus.operator_name == decision.operator_name and
                            (bus.available_seats or 0) > 0 for bus in options)):
                logger.warning("Planner violated explicit bus preference for %s leg", leg)
                raise HTTPException(status_code=503,
                    detail="The planner could not verify a bus itinerary. Please retry or choose another mode.")

    # ── Step 3: Ground the hotel and arrival transfer in provider routes ──
    try:
        itinerary = await _hotel_recommendation.apply(itinerary, context)
    except Exception as exc:
        logger.exception("Hotel recommendation failed: %s", exc)
        raise HTTPException(status_code=503, detail="Hotel recommendation is temporarily unavailable") from exc

    # ── Step 4: Validate choices and calculate costs ──────────────────────
    try:
        itinerary = _validator.validate_and_calculate_costs(itinerary, context)
    except Exception as exc:
        logger.warning("Cost calculation / validation warning: %s", exc)

    return itinerary


@router.post("/check-transport")
async def check_transport(trip: TripRequest):
    """
    Fast endpoint to check transport availability before running full AI planning.
    Returns status of the requested transport mode and class.
    """
    try:
        context = await _orchestrator.build_context(trip)
    except Exception as exc:
        logger.exception("Orchestration failure during /check-transport: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to assemble trip data.")

    pref = trip.preferences.transport
    result = {"status": "NOT_FOUND", "seats": 0}

    if pref.mode == "train":
        trains = context.outbound_trains
        if not trains:
            return result
        
        target_class = pref.berth_preference or "3A"
        # Find best available seat
        best_status = "WL"
        max_seats = 0

        for t in trains:
            for c in t.classes:
                if c.travel_class == target_class:
                    avail_str = (c.availability or "").upper()
                    
                    num_seats = 0
                    if "-" in avail_str:
                        try:
                            num_seats = int(avail_str.split("-")[1])
                        except ValueError:
                            pass
                            
                    if avail_str.startswith("AVAILABLE"):
                        return {"status": "AVL", "seats": num_seats}
                    elif avail_str.startswith("RAC"):
                        best_status = "RAC"
                        max_seats = max(max_seats, num_seats)
                    elif avail_str.startswith("WL") and best_status == "WL":
                        max_seats = max(max_seats, num_seats)
        
        result["status"] = best_status
        result["seats"] = max_seats

    return result
