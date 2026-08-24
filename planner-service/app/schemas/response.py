"""
API response envelope for POST /plan/context.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.context import TripContext


class PlanContextResponse(BaseModel):
    """
    Standard envelope wrapping the TripContext.
    Allows adding top-level metadata (request_id, duration_ms, warnings)
    without changing the TripContext contract.
    """
    success: bool = True
    context: TripContext
