"""
TripRequest schema — the traveler's intent.

Designed for backward-compatible extensibility:
  - Preferences are grouped into dedicated sub-objects.
  - Every preference group is Optional with a default so adding new groups
    never breaks existing callers.
  - Adding a new field to any preference sub-model is always non-breaking
    because new fields use Optional with defaults.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ─────────────────────────────────────────────────────────────

class BudgetLevel(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class TransportPref(str, Enum):
    train  = "train"
    bus    = "bus"
    flight = "flight"
    any    = "any"


class BerthPreference(str, Enum):
    """
    Preferred berth / travel class for trains and buses.

    AC train classes  : 1A (First AC), 2A (Second AC), 3A (Third AC), CC (Chair Car)
    Non-AC classes    : SL (Sleeper), 2S (Second Sitting), GN (General)
    Buses             : ac = AC coach, non_ac = ordinary/sleeper coach
    any               : No preference — show all available classes (default when omitted)

    If a specific class (e.g. "3A") is unavailable on a train, the agent
    will fall back to the next best class within the same AC/Non-AC category.
    """
    any       = "any"
    # ── AC train classes ──────────────────────────────────────────────────────
    first_ac  = "1A"
    second_ac = "2A"
    third_ac  = "3A"
    chair_car = "CC"
    # ── Non-AC train classes ──────────────────────────────────────────────────
    sleeper        = "SL"
    second_sitting = "2S"
    general        = "GN"


class HotelPref(str, Enum):
    budget    = "budget"
    mid_range = "mid_range"
    luxury    = "luxury"
    any       = "any"


class TravelPace(str, Enum):
    relaxed    = "relaxed"
    moderate   = "moderate"
    intensive  = "intensive"


class DietaryRestriction(str, Enum):
    none         = "none"
    vegetarian   = "vegetarian"
    vegan        = "vegan"
    halal        = "halal"
    gluten_free  = "gluten_free"


# ── Preference sub-models ─────────────────────────────────────────────────────

class BudgetPreferences(BaseModel):
    level: BudgetLevel = BudgetLevel.medium


class TransportPreferences(BaseModel):
    mode: TransportPref = TransportPref.any
    berth_preference: Optional[BerthPreference] = Field(
        default=None,
        description=(
            "Preferred berth/class code. One of: 'any', '1A', '2A', '3A', 'CC' (AC trains), "
            "'SL', '2S', 'GN' (Non-AC trains). Omit or set null for no preference."
        ),
    )


class HotelPreferences(BaseModel):
    category: HotelPref = HotelPref.any


class ActivityPreferences(BaseModel):
    pace: TravelPace = TravelPace.moderate
    # Extensible — add interests, accessibility, adventure, etc. here
    interests: list[str] = Field(
        default_factory=list,
        description="e.g. ['history', 'nature', 'photography', 'adventure']",
    )
    family_friendly: Optional[bool] = None
    accessibility: Optional[bool] = None


class FoodPreferences(BaseModel):
    """
    Optional food preference block.
    Adding this field to TripPreferences is non-breaking because it is Optional.
    """
    dietary_restrictions: DietaryRestriction = DietaryRestriction.none
    cuisines: list[str] = Field(
        default_factory=list,
        description="e.g. ['South Indian', 'Chinese', 'Italian']",
    )
    avoid_street_food: bool = False


class TripPreferences(BaseModel):
    """
    Grouped preferences — each domain owns its own sub-object.
    Adding a new preference group here is always non-breaking.
    """
    budget:    BudgetPreferences    = Field(default_factory=BudgetPreferences)
    transport: TransportPreferences = Field(default_factory=TransportPreferences)
    hotel:     HotelPreferences     = Field(default_factory=HotelPreferences)
    activities: ActivityPreferences = Field(default_factory=ActivityPreferences)
    food:      Optional[FoodPreferences] = Field(
        default=None,
        description="Optional. Omit entirely if food preferences are not relevant.",
    )
    # Future groups go here as Optional fields with defaults:
    #   nightlife:  Optional[NightlifePreferences] = None
    #   weather:    Optional[WeatherPreferences]   = None


# ── Top-level TripRequest ─────────────────────────────────────────────────────

class TripRequest(BaseModel):
    """
    The traveler's complete trip specification.
    Sent as the body of POST /plan/context.
    """

    origin:      str = Field(..., min_length=1, description="Departure city.")
    destination: str = Field(..., min_length=1, description="Destination city.")
    start_date:  date = Field(..., description="Trip start date (YYYY-MM-DD).")
    end_date:    date = Field(..., description="Trip end date (YYYY-MM-DD).")
    travelers:   int  = Field(default=2, ge=1, le=20, description="Number of travelers.")

    preferences: TripPreferences = Field(
        default_factory=TripPreferences,
        description="All preference groups. Fully optional — omit for defaults.",
    )

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date.")
        return v
