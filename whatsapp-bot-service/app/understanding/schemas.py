"""
Pydantic schemas for extracted trip slots and intent parsing.
"""

from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field

from app.schemas.trip import BudgetLevel, TransportPref, HotelPref


class ExtractedTripSlots(BaseModel):
    """Normalized structured slots extracted from user text or interactive button clicks."""
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
    
    # Meta / Intent flags
    reset_intent: bool = False
    confirmation_intent: Optional[bool] = None  # True if user clicked Confirm / Yes
    modification_intent: Optional[str] = None   # e.g. "cheaper hotel", "change transport"
    menu_intent: bool = False                   # True if user requested Menu
    past_trips_intent: bool = False             # True if user requested Past / Saved Trips
    resume_intent: bool = False                 # True if user chose to continue / resume
    selected_trip_number: Optional[int] = None  # 1-based index if user replied "Trip 1"
    invalid_city: Optional[str] = None          # Set if candidate place was unrecognized
    is_origin_invalid: bool = False             # True if invalid city was for origin
    suggested_city: Optional[str] = None        # Set if Gemini caught a typo
    typo_confirmed_city: Optional[str] = None   # Set if user clicks 'Yes' on typo prompt
    train_class: Optional[str] = None           # e.g., '3A', '2A', 'SL'
    invalid_date_reason: Optional[str] = None   # Set if ARP constraints are violated

    def has_slots(self) -> bool:
        """Returns True if at least one meaningful slot or intent was identified."""
        return bool(
            self.origin
            or self.destination
            or self.start_date
            or self.end_date
            or self.duration_days
            or self.travelers
            or self.budget_level
            or self.transport_mode
            or self.hotel_category
            or self.interests
            or self.reset_intent
            or self.confirmation_intent is not None
            or self.modification_intent
            or self.menu_intent
            or self.past_trips_intent
            or self.resume_intent
            or self.selected_trip_number is not None
        )
