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
from app.clients.hotel_client import HotelClient
from app.clients.route_client import RouteClient
from app.clients.tourism_client import TourismClient
from app.clients.transport_client import BusClient, TrainClient
from app.orchestration.trip_orchestrator import TripOrchestrator
from app.schemas.itinerary import Itinerary
from app.schemas.request import TripRequest
from app.services.llm.gemini_client import GeminiClient

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Singletons ────────────────────────────────────────────────────────────────
# Orchestrator is shared (has granular in-memory cache).
# GeminiClient + PlanningAgent are lazy — initialised on first request so the
# server starts even if GEMINI_API_KEY is not yet set.

_orchestrator = TripOrchestrator(
    tourism=TourismClient(),
    hotels=HotelClient(),
    buses=BusClient(),
    trains=TrainClient(),
    route=RouteClient(),
)

_agent: PlanningAgent | None = None


def _get_agent() -> PlanningAgent:
    global _agent
    if _agent is None:
        try:
            _agent = PlanningAgent(llm=GeminiClient())
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Planning agent is not configured (GEMINI_API_KEY missing).",
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
        "3. Passes the normalized `TripContext` to the Gemini Planning Agent.\n"
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

    return itinerary
