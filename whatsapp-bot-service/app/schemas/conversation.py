"""
Conversation state machine models, user session models, and persistence records.
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field

from app.schemas.trip import TripDraft, TripRequest


class ConversationState(str, Enum):
    START = "START"
    COLLECT_ORIGIN = "COLLECT_ORIGIN"
    COLLECT_DESTINATION = "COLLECT_DESTINATION"
    COLLECT_DATES = "COLLECT_DATES"
    COLLECT_TRAVELERS = "COLLECT_TRAVELERS"
    COLLECT_BUDGET = "COLLECT_BUDGET"
    COLLECT_TRANSPORT = "COLLECT_TRANSPORT"
    COLLECT_TRAIN_CLASS = "COLLECT_TRAIN_CLASS"
    COLLECT_HOTEL = "COLLECT_HOTEL"
    COLLECT_INTERESTS = "COLLECT_INTERESTS"
    CONFIRM_CITY_TYPO = "CONFIRM_CITY_TYPO"
    HANDLE_WAITLIST_RAC = "HANDLE_WAITLIST_RAC"
    CONFIRM_TRIP = "CONFIRM_TRIP"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    MODIFYING = "MODIFYING"
    RESUME_CHOICE = "RESUME_CHOICE"
    MAIN_MENU = "MAIN_MENU"
    VIEWING_TRIPS = "VIEWING_TRIPS"
    ERROR = "ERROR"


class UserSession(BaseModel):
    """
    Active user conversation state cached in Redis.
    Key: travel:conversation:{wa_id}
    """
    conversation_id: str = Field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}")
    wa_id: str
    user_name: str = "Traveler"
    state: ConversationState = ConversationState.START
    paused_state: Optional[ConversationState] = None
    draft: TripDraft = Field(default_factory=TripDraft)
    current_trip_id: Optional[str] = None
    last_message_id: Optional[str] = None
    last_activity: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    correlation_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}")

    def touch(self, message_id: Optional[str] = None):
        """Update last activity and increment state version."""
        self.last_activity = datetime.now(timezone.utc).isoformat()
        self.version += 1
        if message_id:
            self.last_message_id = message_id


class UserRecord(BaseModel):
    """Durable user record in Firestore at users/{wa_id}"""
    wa_id: str
    display_name: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    preferences: Dict[str, Any] = Field(default_factory=dict)


class MessageRecord(BaseModel):
    """Audit log of message in Firestore at users/{wa_id}/conversations/{conv_id}/messages/{msg_id}"""
    message_id: str
    direction: str  # inbound or outbound
    message_type: str
    text: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "processed"


class ConversationRecord(BaseModel):
    """Durable conversation history in Firestore at users/{wa_id}/conversations/{conv_id}"""
    conversation_id: str
    wa_id: str
    status: str = "active"  # active, completed, abandoned
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    current_state: str = ConversationState.START.value
    trip_id: Optional[str] = None


class ItineraryVersionRecord(BaseModel):
    """Itinerary version record in Firestore at users/{wa_id}/trips/{trip_id}/itineraries/{version_id}"""
    version_id: str = Field(default_factory=lambda: f"v_{uuid.uuid4().hex[:8]}")
    version_number: int = 1
    itinerary_data: Dict[str, Any]
    modification_prompt: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_current: bool = True


class TripRecord(BaseModel):
    """Durable trip record in Firestore at users/{wa_id}/trips/{trip_id}"""
    trip_id: str = Field(default_factory=lambda: f"trip_{uuid.uuid4().hex[:10]}")
    wa_id: str
    conversation_id: str
    origin: str
    destination: str
    start_date: str
    end_date: str
    travelers: int
    status: str = "generated"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latest_version: int = 1
    trip_request_data: Dict[str, Any]
