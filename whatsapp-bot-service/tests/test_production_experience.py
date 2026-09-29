"""
Comprehensive test suite verifying:
1. Guardrail Shield (in-scope vs off-topic strictly dropped)
2. Conversation Inactivity & Resumption Choice (handling "hi" after previous trip)
3. Centralized Main Menu & Past Itineraries retrieval
4. Executive Visual Itinerary formatting with clickable Google Maps links
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.schemas.conversation import ConversationState, UserSession
from app.schemas.trip import TripDraft, BudgetLevel, TransportPref, HotelPref
from app.schemas.webhook import NormalizedEvent, MessageType
from app.understanding.guardrail import guardrail_shield
from app.understanding.message_parser import message_parser
from app.conversation.state_machine import StateMachine
from app.conversation.manager import conversation_manager
from app.whatsapp.messages import format_itinerary_message
from app.storage.redis_store import redis_store


@pytest.mark.asyncio
async def test_guardrail_shield():
    # In-scope queries
    assert await guardrail_shield.is_in_scope("hi") is True
    assert await guardrail_shield.is_in_scope("Menu") is True
    assert await guardrail_shield.is_in_scope("Plan a trip to Goa") is True
    assert await guardrail_shield.is_in_scope("3 days for 2 people", None) is True
    assert await guardrail_shield.is_in_scope(None, "btn_dates_weekend") is True

    # Off-topic queries (Strict rejection)
    assert await guardrail_shield.is_in_scope("write python code to sort a list") is False
    assert await guardrail_shield.is_in_scope("def calculate_sum(a, b): return a + b") is False
    assert await guardrail_shield.is_in_scope("who is the president of france") is False
    assert await guardrail_shield.is_in_scope("solve equation 5x + 3 = 18") is False
    assert await guardrail_shield.is_in_scope("recipe for baking chocolate cake") is False


@pytest.mark.asyncio
async def test_inactivity_resumption_flow():
    wa_id = "919876543210"
    session = UserSession(wa_id=wa_id, user_name="Traveler")
    session.draft.destination = "Mumbai"
    session.draft.origin = "Rajapalayam"
    session.state = ConversationState.COMPLETED
    # Simulate message from yesterday
    session.last_activity = (datetime.now(timezone.utc) - timedelta(hours=14)).isoformat()
    await redis_store.save_session(session)

    # When user sends "hi" today
    event = NormalizedEvent(
        wa_id=wa_id,
        user_name="Traveler",
        message_id="msg_hi_test_1",
        timestamp=str(int(datetime.now().timestamp())),
        message_type=MessageType.TEXT,
        text="hi",
    )
    await conversation_manager.process_incoming_event(event)

    # Check that session transitioned to RESUME_CHOICE and did NOT spit out raw completed text
    updated = await redis_store.get_session(wa_id)
    assert updated.state == ConversationState.RESUME_CHOICE


@pytest.mark.asyncio
async def test_resumption_choice_actions():
    wa_id = "919876543211"
    session = UserSession(wa_id=wa_id, user_name="Traveler")
    session.draft.destination = "Goa"
    session.state = ConversationState.RESUME_CHOICE
    session.paused_state = ConversationState.COLLECT_BUDGET
    await redis_store.save_session(session)

    # User chooses to continue
    event = NormalizedEvent(
        wa_id=wa_id,
        user_name="Traveler",
        message_id="msg_resume_test",
        timestamp=str(int(datetime.now().timestamp())),
        message_type=MessageType.BUTTON,
        payload_id="btn_resume_trip",
    )
    await conversation_manager.process_incoming_event(event)

    updated = await redis_store.get_session(wa_id)
    assert updated.state == ConversationState.COLLECT_BUDGET

    # User chooses to start over
    event_start_over = NormalizedEvent(
        wa_id=wa_id,
        user_name="Traveler",
        message_id="msg_start_over_test",
        timestamp=str(int(datetime.now().timestamp())),
        message_type=MessageType.BUTTON,
        payload_id="btn_start_over",
    )
    await conversation_manager.process_incoming_event(event_start_over)

    updated_reset = await redis_store.get_session(wa_id)
    assert updated_reset.state == ConversationState.START
    assert updated_reset.draft.destination is None


@pytest.mark.asyncio
async def test_centralized_main_menu():
    wa_id = "919876543212"
    session = UserSession(wa_id=wa_id, user_name="Traveler")
    session.state = ConversationState.COLLECT_ORIGIN
    session.draft.destination = "Ooty"
    await redis_store.save_session(session)

    event = NormalizedEvent(
        wa_id=wa_id,
        user_name="Traveler",
        message_id="msg_menu_test",
        timestamp=str(int(datetime.now().timestamp())),
        message_type=MessageType.TEXT,
        text="Menu",
    )
    await conversation_manager.process_incoming_event(event)

    updated = await redis_store.get_session(wa_id)
    assert updated.state == ConversationState.MAIN_MENU
    assert updated.paused_state == ConversationState.COLLECT_ORIGIN


@pytest.mark.asyncio
async def test_past_trips_archiving_and_retrieval():
    wa_id = "919876543213"
    trip_sample = {
        "trip_id": "trip_test_001",
        "origin": "Chennai",
        "destination": "Goa",
        "days": 4,
        "travelers": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "itinerary_data": {
            "summary": {"days": 4, "travelers": 2, "budget_level": "medium", "pace": "relaxed"},
            "days": [
                {
                    "day": 1,
                    "theme": "Arrival & Beach Sunset",
                    "activities": [
                        {
                            "attraction_name": "Baga Beach",
                            "start_time": "04:30 PM",
                            "duration_minutes": 120,
                            "notes": "Sunset stroll and beach shacks",
                        }
                    ],
                }
            ],
        },
    }
    await redis_store.save_user_trip(wa_id, trip_sample)

    trips = await redis_store.get_user_trips(wa_id, limit=5)
    assert len(trips) >= 1
    assert trips[0]["destination"] == "Goa"

    # User asks for past trips
    event = NormalizedEvent(
        wa_id=wa_id,
        user_name="Traveler",
        message_id="msg_past_trips",
        timestamp=str(int(datetime.now().timestamp())),
        message_type=MessageType.TEXT,
        text="Past trips",
    )
    await conversation_manager.process_incoming_event(event)

    updated = await redis_store.get_session(wa_id)
    assert updated.state == ConversationState.VIEWING_TRIPS


def test_visual_itinerary_formatting():
    itinerary_data = {
        "summary": {
            "origin": "Rajapalayam",
            "destination": "Mumbai",
            "days": 5,
            "travelers": 4,
            "budget_level": "medium",
            "pace": "moderate",
        },
        "outbound_transport": {
            "mode": "Train",
            "train_name": "Mumbai Express",
            "train_number": "12617",
            "departure_station": "Madurai Junction",
            "arrival_station": "Mumbai CSMT",
            "departure_time": "08:00 PM",
            "arrival_time": "11:30 AM",
            "fare_per_person": 1850,
        },
        "hotel": {
            "hotel_name": "Hotel Marine Plaza",
            "price_per_night": 4500,
            "price_total": 18000,
            "reasoning": "Excellent Sea view at Marine Drive",
        },
        "days": [
            {
                "day": 1,
                "theme": "Heritage South Mumbai",
                "activities": [
                    {
                        "attraction_name": "Gateway of India",
                        "start_time": "09:30 AM",
                        "duration_minutes": 90,
                        "notes": "Historic waterfront monument",
                        "estimated_cost": 0,
                    },
                    {
                        "attraction_name": "Elephanta Caves",
                        "start_time": "11:30 AM",
                        "duration_minutes": 180,
                        "notes": "Ferry ride and ancient rock-cut caves",
                        "estimated_cost": 260,
                    },
                ],
            }
        ],
        "cost_breakdown": {
            "transport_cost": 7400,
            "hotel_cost": 18000,
            "activities_estimated_cost": 4000,
            "total_cost": 29400,
        },
    }

    formatted = format_itinerary_message(itinerary_data, "Rajapalayam", "Mumbai")

    # Verify no raw dict/json emitted
    assert "{'destination':" not in formatted
    assert "{" not in formatted
    assert "}" not in formatted

    # Verify neat formatting and maps links
    assert "RAJAPALAYAM ➔ MUMBAI EXPEDITION" in formatted
    assert "Gateway of India" in formatted
    assert "https://maps.google.com/?q=Gateway+of+India%2C+Mumbai" in formatted
    assert "https://maps.google.com/?q=Hotel+Marine+Plaza%2C+Mumbai" in formatted
    assert "₹29,400" in formatted
    assert "━━━━━━━━━━━━━━━━━━━━" in formatted
