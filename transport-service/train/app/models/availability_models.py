"""
Pydantic Models for Train Seat Availability

Provides strict validation and schema typing for availability requests and responses.
"""

from __future__ import annotations

import re
from datetime import datetime, date as dt_date, timedelta
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


VALID_CLASSES = {
    "1A", "2A", "3A", "3E", "SL", "CC", "2S", "EC", "EA", "FC", "GN"
}

VALID_QUOTAS = {
    "GN", "TQ", "PT", "LD", "SS", "DF", "FT", "HP", "DP", "OS", "RAC"
}


class AvailabilityRequest(BaseModel):
    """
    Validated request model for train seat availability check.
    Supports both camelCase aliases (for query params / Ixigo style) and snake_case.
    """
    train_no: str = Field(
        ...,
        alias="trainNo",
        description="4 to 5 digit IRCTC train number (e.g. '16102', '12626')",
        examples=["16102", "12626"]
    )
    source: str = Field(
        ...,
        description="2 to 5 character uppercase IRCTC source station code (e.g. 'RJPM')",
        examples=["RJPM", "MAS", "NDLS"]
    )
    destination: str = Field(
        ...,
        description="2 to 5 character uppercase IRCTC destination station code (e.g. 'SVKS')",
        examples=["SVKS", "MDU", "CSMT"]
    )
    travel_class: str = Field(
        ...,
        alias="travelClass",
        description="IRCTC travel class code (e.g. 'SL', '3A', '2A', '1A', 'CC', '2S')",
        examples=["SL", "3A"]
    )
    date: str = Field(
        ...,
        description="Date of journey in DD-MM-YYYY or YYYY-MM-DD format",
        examples=["26-08-2026", "2026-08-26"]
    )
    quota: str = Field(
        default="GN",
        description="IRCTC quota code (default: 'GN')",
        examples=["GN", "TQ", "PT"]
    )

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True
    }

    @field_validator("train_no")
    @classmethod
    def validate_train_number(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^\d{4,5}$", clean):
            raise ValueError(f"Invalid train number '{v}'. Must be a 4 or 5 digit numeric code.")
        return clean

    @field_validator("source", "destination")
    @classmethod
    def validate_station_code(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(r"^[A-Z]{2,5}$", clean):
            raise ValueError(f"Invalid station code '{v}'. Must be 2-5 uppercase alphabetic characters.")
        return clean

    @field_validator("travel_class")
    @classmethod
    def validate_travel_class(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_CLASSES:
            raise ValueError(f"Invalid travel class '{v}'. Must be one of: {sorted(VALID_CLASSES)}.")
        return clean

    @field_validator("quota")
    @classmethod
    def validate_quota(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_QUOTAS:
            raise ValueError(f"Invalid quota '{v}'. Must be one of: {sorted(VALID_QUOTAS)}.")
        return clean

    @field_validator("date")
    @classmethod
    def validate_and_normalize_date(cls, v: str) -> str:
        clean = v.strip()
        parsed_dt: Optional[datetime] = None

        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                parsed_dt = datetime.strptime(clean, fmt)
                break
            except ValueError:
                continue

        if parsed_dt is None:
            raise ValueError(f"Invalid date format '{v}'. Expected DD-MM-YYYY or YYYY-MM-DD.")

        # Journey date range check (IRCTC advance booking window is 120 days)
        # Allow yesterday to account for timezone differences or trains departing across midnight
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).date()
        max_advance = (now + timedelta(days=125)).date()

        if parsed_dt.date() < yesterday:
            raise ValueError(f"Journey date {clean} is in the past.")
        if parsed_dt.date() > max_advance:
            raise ValueError(f"Journey date {clean} exceeds maximum 120-day IRCTC booking window.")

        # Return standardized DD-MM-YYYY format expected by upstream API
        return parsed_dt.strftime("%d-%m-%Y")

    @model_validator(mode="after")
    def validate_distinct_stations(self) -> AvailabilityRequest:
        if self.source == self.destination:
            raise ValueError("Source and destination station codes cannot be identical.")
        return self


class AvailabilityData(BaseModel):
    train_number: str
    travel_class: str
    quota: str
    availability: str
    booking_status: Literal["AVAILABLE", "RAC", "WL", "REGRET", "UNKNOWN"]
    prediction: int = 0
    fare: int = 0
    total_fare: int = 0
    booking_enabled: bool = True
    last_updated: str
    next_available_dates: List[str] = Field(default_factory=list)


class AvailabilityResponse(BaseModel):
    success: bool
    message: str
    data: Optional[AvailabilityData] = None
