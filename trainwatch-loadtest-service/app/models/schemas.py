"""
Data schemas and models for TrainWatch Availability Load-Test Service.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class ScenarioType(str, Enum):
    """Supported load test scenario patterns."""

    BALANCED = "balanced"  # 50% identical hot query, 50% diverse queries
    BURST_IDENTICAL = "burst_identical"  # 100% identical canonical key (tests Singleflight)
    DIVERSE_MATRIX = "diverse_matrix"  # 100% different stations/classes/dates
    CUSTOM = "custom"  # User-specified payloads in request body


class TrainQueryPayload(BaseModel):
    """
    Individual train seat availability payload sent to target API.
    Uses camelCase aliases matching the production endpoint requirements.
    """

    train_no: str = Field(..., alias="trainNo", description="Train number (e.g. 06030)")
    source: str = Field(..., description="Source station code (e.g. TEN)")
    destination: str = Field(..., description="Destination station code (e.g. MTP)")
    travel_class: str = Field(..., alias="travelClass", description="Travel class (e.g. SL, 3A, 2A)")
    date: str = Field(..., description="Date of journey (DD-MM-YYYY)")
    quota: str = Field(default="GN", description="Quota (default: GN)")

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True,
    }

    @property
    def canonical_key(self) -> str:
        """Unique deduplication key representing this exact query combination."""
        return f"{self.train_no}:{self.source}:{self.destination}:{self.date}:{self.travel_class}:{self.quota}"

    def to_api_payload(self) -> Dict[str, str]:
        """Convert to dict with exact keys expected by production API."""
        return {
            "trainNo": self.train_no,
            "source": self.source,
            "destination": self.destination,
            "travelClass": self.travel_class,
            "date": self.date,
            "quota": self.quota,
        }


class RunRequest(BaseModel):
    """Request payload for triggering POST /run."""

    scenario: ScenarioType = Field(
        default=ScenarioType.BALANCED,
        description="Load scenario pattern to execute",
    )
    concurrency: Optional[int] = Field(
        default=None,
        description="Number of concurrent asynchronous workers (capped by server max)",
        ge=1,
    )
    total_requests: Optional[int] = Field(
        default=None,
        description="Total number of simulated user requests (capped by server max)",
        ge=1,
    )
    custom_payloads: Optional[List[TrainQueryPayload]] = Field(
        default=None,
        description="Explicit payloads when scenario='custom'",
    )
    timeout_seconds: Optional[float] = Field(
        default=None,
        description="Per-request timeout in seconds",
        ge=1.0,
        le=30.0,
    )

    @model_validator(mode="after")
    def validate_custom_payloads(self) -> RunRequest:
        if self.scenario == ScenarioType.CUSTOM and not self.custom_payloads:
            raise ValueError("custom_payloads must be provided when scenario='custom'")
        return self


class RequestMetric(BaseModel):
    """Raw telemetry record for an individual simulated request."""

    request_index: int
    canonical_key: str
    status_code: int
    latency_ms: float
    success: bool
    error: Optional[str] = None
    response_timestamp: Optional[str] = None
    booking_status: Optional[str] = None
    correlation_id: Optional[str] = None
    api_response: Optional[Dict[str, Any]] = None


class CanonicalKeyStats(BaseModel):
    """Aggregated statistics for a specific canonical query key."""

    canonical_key: str
    simulated_requests: int
    successful_requests: int
    failed_requests: int
    status_codes: Dict[str, int]
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    deduplication_confirmed: bool
    efficiency_ratio: float
    sample_response: Optional[Dict[str, Any]] = None


class LatencySummary(BaseModel):
    """Summary of response latencies in milliseconds."""

    min_ms: float
    avg_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


class RunSummary(BaseModel):
    """Complete summary of a load test run persisted to Firestore."""

    run_id: str
    timestamp: str
    scenario: str
    target_url: str
    total_simulated_requests: int
    unique_canonical_keys: int
    deduplication_ratio: float
    success_count: int
    client_error_count: int
    server_error_count: int
    total_duration_sec: float
    throughput_rps: float
    latency: LatencySummary
    deduplication_verified: bool
    firestore_persisted: bool
    firestore_doc_id: Optional[str] = None
    api_responses: Dict[str, Any] = Field(
        default_factory=dict,
        description="Live train availability response payloads returned by upstream API, keyed by canonical route key",
    )
    key_breakdown: List[CanonicalKeyStats]
    errors: List[str] = []


class HealthResponse(BaseModel):
    """Service health response."""

    status: str
    service: str
    version: str
    firestore_enabled: bool
    active_run: bool
