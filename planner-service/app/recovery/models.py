from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.request import TripRequest


class Commitment(BaseModel):
    id: str
    kind: Literal["transport", "stay", "activity", "other"]
    title: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    confirmed: bool = False
    cost: float | None = Field(default=None, ge=0)
    currency: str = "INR"
    notes: str | None = None

    @model_validator(mode="after")
    def check_times(self):
        for value in (self.starts_at, self.ends_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("Commitment timestamps need timezone offsets")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("Commitment end must be after start")
        return self


class RecoveryRequest(BaseModel):
    trip: TripRequest
    itinerary: dict[str, Any] = Field(default_factory=dict)
    change: str = Field(min_length=5, max_length=1000)
    commitments: list[Commitment] = Field(default_factory=list)
    trip_id: str | None = None
    event_id: str | None = None


class Evidence(BaseModel):
    provider: str
    fetched_at: datetime
    valid_until: datetime
    source_status: Literal["search_result", "schedule", "estimate"]


class RecoveryOption(BaseModel):
    id: str
    category: Literal["mobility", "experience", "keep"]
    title: str
    reason: str
    price: float | None = Field(default=None, ge=0)
    currency: str = "INR"
    departure_time: str | None = None
    arrival_time: str | None = None
    source_id: str | None = None
    evidence: Evidence | None = None
    warnings: list[str] = Field(default_factory=list)


class AgentTrace(BaseModel):
    agent: str
    tools: list[str] = Field(default_factory=list)
    considered: int = 0
    selected: list[str] = Field(default_factory=list)
    status: str = "ok"


class RecoveryResult(BaseModel):
    status: Literal["ready", "needs_clarification", "no_verified_options"]
    change_kind: Literal["delay", "cancellation", "closure", "preference", "unknown"]
    affected_commitment_ids: list[str] = Field(default_factory=list)
    clarification: str | None = None
    options: list[RecoveryOption] = Field(default_factory=list)
    traces: list[AgentTrace] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    disclaimer: str = "Search results are not bookings. Recheck availability before paying."
