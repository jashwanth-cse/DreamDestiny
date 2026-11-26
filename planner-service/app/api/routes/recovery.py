from fastapi import APIRouter, HTTPException

from app.clients.flight_client import FlightClient
from app.clients.hotel_client import HotelClient
from app.clients.route_client import RouteClient
from app.clients.tourism_client import TourismClient
from app.clients.transport_client import BusClient, TrainClient
from app.orchestration.trip_orchestrator import TripOrchestrator
from app.recovery.models import RecoveryRequest, RecoveryResult
from app.recovery.service import RecoveryService
from app.services.llm.llm_client import BedrockLLMClient

router = APIRouter(prefix="/v1/recovery", tags=["Trip Rescue"])
def get_recovery_service():
    # A fresh orchestrator avoids the ordinary planner's 15-minute result cache.
    # Recovery must re-query providers before presenting or applying an option.
    orchestrator = TripOrchestrator(tourism=TourismClient(), hotels=HotelClient(),
        buses=BusClient(), trains=TrainClient(), route=RouteClient(), flights=FlightClient())
    return RecoveryService(orchestrator, BedrockLLMClient())


@router.post("", response_model=RecoveryResult)
async def propose_recovery(request: RecoveryRequest):
    try:
        return await get_recovery_service().recover(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Recovery model is not configured") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Recovery data is currently unavailable") from exc
