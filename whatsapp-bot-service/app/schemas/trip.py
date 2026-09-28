"""
TripRequest and TripDraft schemas aligned with the existing Planner backend.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class BudgetLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TransportPref(str, Enum):
    train = "train"
    bus = "bus"
    flight = "flight"
    any = "any"


class BerthPreference(str, Enum):
    any = "any"
    first_ac = "1A"
    second_ac = "2A"
    third_ac = "3A"
    chair_car = "CC"
    sleeper = "SL"
    second_sitting = "2S"
    general = "GN"


class HotelPref(str, Enum):
    budget = "budget"
    mid_range = "mid_range"
    luxury = "luxury"
    any = "any"


class TravelPace(str, Enum):
    relaxed = "relaxed"
    moderate = "moderate"
    intensive = "intensive"


class BudgetPreferences(BaseModel):
    level: BudgetLevel = BudgetLevel.medium


class TransportPreferences(BaseModel):
    mode: TransportPref = TransportPref.any
    berth_preference: Optional[BerthPreference] = None


class HotelPreferences(BaseModel):
    category: HotelPref = HotelPref.any


class ActivityPreferences(BaseModel):
    pace: TravelPace = TravelPace.moderate
    interests: List[str] = Field(default_factory=list)
    family_friendly: Optional[bool] = None
    accessibility: Optional[bool] = None


class TripPreferences(BaseModel):
    budget: BudgetPreferences = Field(default_factory=BudgetPreferences)
    transport: TransportPreferences = Field(default_factory=TransportPreferences)
    hotel: HotelPreferences = Field(default_factory=HotelPreferences)
    activities: ActivityPreferences = Field(default_factory=ActivityPreferences)


class TripRequest(BaseModel):
    """The traveler's complete trip specification matching planner-service schema."""
    origin: str = Field(..., min_length=1, description="Departure city.")
    destination: str = Field(..., min_length=1, description="Destination city.")
    start_date: date = Field(..., description="Trip start date (YYYY-MM-DD).")
    end_date: date = Field(..., description="Trip end date (YYYY-MM-DD).")
    travelers: int = Field(default=2, ge=1, le=20, description="Number of travelers.")
    preferences: TripPreferences = Field(default_factory=TripPreferences)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date.")
        return v


class TripDraft(BaseModel):
    """
    Mutable in-progress trip draft stored in Redis during slot-filling.
    Fields start None until collected from user input.
    """
    origin: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: Optional[int] = None
    travelers: Optional[int] = None
    budget_level: Optional[BudgetLevel] = None
    transport_mode: Optional[TransportPref] = None
    hotel_category: Optional[HotelPref] = None
    interests: List[str] = Field(default_factory=list)

    def is_complete_for_planning(self) -> bool:
        """Check if minimum required fields to call /plan are present."""
        return bool(
            self.origin
            and self.destination
            and self.start_date
            and self.end_date
            and (self.travelers or 2)
        )

    def to_trip_request(self) -> TripRequest:
        """Convert collected draft into strict TripRequest for the Planner Gateway."""
        if not self.is_complete_for_planning():
            raise ValueError("TripDraft is incomplete. Cannot build TripRequest.")

        return TripRequest(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            travelers=self.travelers or 2,
            preferences=TripPreferences(
                budget=BudgetPreferences(level=self.budget_level or BudgetLevel.medium),
                transport=TransportPreferences(mode=self.transport_mode or TransportPref.any),
                hotel=HotelPreferences(category=self.hotel_category or HotelPref.any),
                activities=ActivityPreferences(interests=self.interests or []),
            ),
        )
