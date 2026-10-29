"""
Train Schedule API Endpoints
"""

from typing import Optional
from fastapi import APIRouter, Depends, Path, Query, Response

from app.exceptions import InvalidRequestError
from app.models.response_models import ErrorResponse
from app.models.schedule_models import TrainScheduleResponse
from app.services.schedule_service import ScheduleService, get_schedule_service

router = APIRouter()

# Standard HTTP cache directive for static train schedules: 24h fresh, 1h stale-while-revalidate
SCHEDULE_CACHE_CONTROL = "public, max-age=86400, stale-while-revalidate=3600"


@router.get(
    "/schedule",
    response_model=TrainScheduleResponse,
    summary="Get Train Schedule (Query Param)",
    description="Retrieves normalized chronological stop schedule, timings, halts, distances, and day counts for a train.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid train number format"},
        404: {"model": ErrorResponse, "description": "Train not found or schedule unavailable"},
        502: {"model": ErrorResponse, "description": "Upstream service error"},
        503: {"model": ErrorResponse, "description": "Service temporarily unavailable due to upstream outage"},
        504: {"model": ErrorResponse, "description": "Upstream timeout"},
    },
)
async def get_schedule_by_query(
    response: Response,
    trainNo: Optional[str] = Query(None, description="4 or 5 digit train number e.g. '12661'"),
    train_no: Optional[str] = Query(None, description="Snake_case alternative for train number"),
    service: ScheduleService = Depends(get_schedule_service),
) -> TrainScheduleResponse:
    """Query parameter endpoint for retrieving train schedule."""
    target_no = trainNo or train_no
    if not target_no:
        raise InvalidRequestError("Query parameter 'trainNo' is required")
    data = await service.get_schedule(target_no)
    response.headers["Cache-Control"] = SCHEDULE_CACHE_CONTROL
    return TrainScheduleResponse(
        success=True,
        message="Train schedule retrieved successfully",
        data=data,
    )


@router.get(
    "/{train_no}/schedule",
    response_model=TrainScheduleResponse,
    summary="Get Train Schedule (Path Param)",
    description="Retrieves normalized chronological stop schedule, timings, halts, distances, and day counts for a train.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid train number format"},
        404: {"model": ErrorResponse, "description": "Train not found or schedule unavailable"},
        502: {"model": ErrorResponse, "description": "Upstream service error"},
        503: {"model": ErrorResponse, "description": "Service temporarily unavailable due to upstream outage"},
        504: {"model": ErrorResponse, "description": "Upstream timeout"},
    },
)
async def get_schedule_by_path(
    response: Response,
    train_no: str = Path(..., description="4 or 5 digit train number e.g. '12661'"),
    service: ScheduleService = Depends(get_schedule_service),
) -> TrainScheduleResponse:
    """RESTful path parameter endpoint for retrieving train schedule."""
    data = await service.get_schedule(train_no)
    response.headers["Cache-Control"] = SCHEDULE_CACHE_CONTROL
    return TrainScheduleResponse(
        success=True,
        message="Train schedule retrieved successfully",
        data=data,
    )
