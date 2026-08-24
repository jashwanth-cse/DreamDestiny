"""
POST /plan/context

Validates TripRequest, delegates to TripOrchestrator, returns TripContext.
No business logic here — this is a thin HTTP adapter.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.clients.hotel_client import HotelClient
from app.clients.route_client import RouteClient
from app.clients.tourism_client import TourismClient
from app.clients.transport_client import BusClient, TrainClient
from app.orchestration.trip_orchestrator import TripOrchestrator
from app.schemas.request import TripRequest
from app.schemas.response import PlanContextResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Dependency wiring ─────────────────────────────────────────────────────────
# Concrete clients are wired here — the orchestrator itself only knows
# about provider interfaces.  To swap a provider, change only this section.

def _get_orchestrator() -> TripOrchestrator:
    return TripOrchestrator(
        tourism = TourismClient(),
        hotels  = HotelClient(),
        buses   = BusClient(),
        trains  = TrainClient(),
        route   = RouteClient(),
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/plan/context",
    response_model=PlanContextResponse,
    summary="Build a complete trip context",
    description=(
        "Validates the trip request, concurrently collects data from all "
        "registered services (tourism, hotels, transport, route), "
        "normalizes responses into a unified TripContext, and returns it.\n\n"
        "Partial results are returned if individual services are unavailable. "
        "Check `context.service_status` to see which services responded.\n\n"
        "**Contains no LLM logic. Contains no business optimization logic.**"
    ),
    responses={
        400: {"description": "Invalid TripRequest"},
        500: {"description": "Orchestration failure"},
    },
)
async def plan_context(trip: TripRequest) -> PlanContextResponse:
    """
    Build a TripContext for the given TripRequest.

    All downstream service calls run concurrently.
    Individual service failures produce empty lists, not errors.
    """
    orchestrator = _get_orchestrator()
    try:
        context = await orchestrator.build_context(trip)
    except Exception as exc:
        logger.exception("Orchestration failure: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Trip context assembly failed. Please try again.",
        )

    return PlanContextResponse(success=True, context=context)
