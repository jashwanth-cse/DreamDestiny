"""
Train Availability API Route

Handles live IRCTC seat availability lookups.
Maintains 100% backward compatibility with existing query parameter clients
while supporting modern JSON body payloads and non-blocking asynchronous execution.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Body, HTTPException, status
from pydantic import ValidationError

from app.models.availability_models import (
    AvailabilityRequest,
    AvailabilityResponse,
)
from app.services.availability_service import (
    AvailabilityService,
    get_availability_service,
)
from app.exceptions import (
    UpstreamTimeoutError,
    UpstreamConnectionError,
    UpstreamServiceError,
    CircuitBreakerOpenError,
)

router = APIRouter()


@router.post(
    "",
    response_model=AvailabilityResponse,
    summary="Get Live Train Availability",
    description=(
        "Fetch live IRCTC seat availability, fares, and predictions for a train and class. "
        "Accepts parameters either via query string or JSON request body."
    ),
    responses={
        200: {"model": AvailabilityResponse, "description": "Availability retrieved successfully"},
        400: {"description": "Invalid request parameters or validation error"},
        404: {"description": "Train or route schedule not found"},
        502: {"description": "Upstream availability provider failure"},
        503: {"description": "Upstream circuit breaker open / service unavailable"},
        504: {"description": "Upstream availability provider timeout"},
    },
)
async def get_availability(
    # Query parameters for backward compatibility
    trainNo: Optional[str] = Query(None, description="Train Number (e.g. 16102)"),
    source: Optional[str] = Query(None, description="Source Station Code (e.g. RJPM)"),
    destination: Optional[str] = Query(None, description="Destination Station Code (e.g. SVKS)"),
    travelClass: Optional[str] = Query(None, description="Travel Class (e.g. SL, 3A)"),
    date: Optional[str] = Query(None, description="Date of Journey (DD-MM-YYYY)"),
    quota: Optional[str] = Query(None, description="Quota (default GN)"),
    # Optional JSON body for REST clients
    body: Optional[AvailabilityRequest] = Body(None),
    availability_service: AvailabilityService = Depends(get_availability_service),
) -> Dict[str, Any]:
    """
    Executes live train availability check with non-blocking async I/O.
    """
    # 1. Resolve request from either query parameters or body
    if body is not None and not any([trainNo, source, destination, travelClass, date]):
        validated_request = body
    else:
        # Build from query parameters
        if not all([trainNo, source, destination, travelClass, date]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required parameters: trainNo, source, destination, travelClass, and date are required.",
            )
        try:
            validated_request = AvailabilityRequest(
                trainNo=trainNo,  # type: ignore
                source=source,  # type: ignore
                destination=destination,  # type: ignore
                travelClass=travelClass,  # type: ignore
                date=date,  # type: ignore
                quota=quota or "GN",
            )
        except (ValidationError, ValueError) as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

    # 2. Asynchronously fetch availability via service layer
    try:
        result = await availability_service.async_fetch_availability(validated_request)
    except UpstreamTimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream availability provider timed out. Please retry shortly.",
        )
    except CircuitBreakerOpenError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Availability service is temporarily unavailable due to upstream provider outage.",
        )
    except (UpstreamConnectionError, UpstreamServiceError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream availability provider returned an error. Please try again.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while checking train availability.",
        )

    # 3. Handle domain not-found or failure responses
    if not result.get("success"):
        message = result.get("message", "Failed to fetch availability")
        if "not found" in message.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return result
