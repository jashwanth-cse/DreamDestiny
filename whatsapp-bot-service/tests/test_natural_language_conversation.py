"""
Test suite verifying natural language flexibility and conversational flow for WhatsApp.
Tests the exact scenarios and expressions encountered in real user conversations:
- Single city answer in COLLECT_ORIGIN ("Chennai", "Rajapalayam")
- Multi-slot travel request ("Plan a trip to Goa for 3 days from Rajapalayam")
- Natural month ranges ("October 10 - 16")
- Month with duration ("From October 7 for 4 days")
- Date ranges ("15-10-2026 to 19-10-2026")
- Contextual affirmation ("Yes take it", "Yes")
"""

import pytest
from datetime import date
from app.schemas.conversation import ConversationState, UserSession
from app.schemas.trip import TripDraft, BudgetLevel
from app.understanding.message_parser import message_parser
from app.conversation.state_machine import StateMachine


def test_origin_city_contextual_parsing():
    """When bot asks for origin, bare city name 'Chennai' must be extracted as origin."""
    slots = message_parser.parse_deterministic("Chennai", current_state=ConversationState.COLLECT_ORIGIN)
    assert slots.origin == "Chennai"

    slots2 = message_parser.parse_deterministic("from Rajapalayam", current_state=ConversationState.COLLECT_ORIGIN)
    assert slots2.origin == "Rajapalayam"


def test_destination_city_contextual_parsing():
    """When bot asks for destination, bare city name 'Goa' must be extracted."""
    slots = message_parser.parse_deterministic("Goa", current_state=ConversationState.COLLECT_DESTINATION)
    assert slots.destination == "Goa"


def test_multi_slot_travel_phrase():
    """Full travel phrase extracts destination, origin, and duration."""
    phrase = "Plan a trip to Goa for 3 days from Rajapalayam"
    slots = message_parser.parse_deterministic(phrase)
    assert slots.destination == "Goa"
    assert slots.origin == "Rajapalayam"
    assert slots.duration_days == 3


def test_natural_language_date_ranges():
    """Extracts start date, end date, and duration from month ranges."""
    slots = message_parser.parse_deterministic("October 10 - 16")
    assert slots.start_date is not None
    assert slots.end_date is not None
    assert slots.start_date.month == 10
    assert slots.start_date.day == 10
    assert slots.end_date.month == 10
    assert slots.end_date.day == 16
    assert slots.duration_days == 6


def test_month_with_duration():
    """Extracts start date and calculates end date from duration."""
    slots = message_parser.parse_deterministic("From October 7 for 4 days")
    assert slots.start_date is not None
    assert slots.start_date.month == 10
    assert slots.start_date.day == 7
    assert slots.duration_days == 4
    assert slots.end_date == slots.start_date.replace(day=11)


def test_explicit_dmy_date_range():
    """Extracts both dates from '15-10-2026 to 19-10-2026'."""
    slots = message_parser.parse_deterministic("15-10-2026 to 19-10-2026")
    assert slots.start_date == date(2026, 10, 15)
    assert slots.end_date == date(2026, 10, 19)
    assert slots.duration_days == 4


def test_state_machine_advances_on_affirmation_in_dates():
    """State machine must NOT loop when user says 'Yes take it' or 'Yes' during date collection."""
    session = UserSession(wa_id="919597747827", user_name="Jashwanth")
    session.state = ConversationState.COLLECT_DATES
    session.draft = TripDraft(destination="Goa", origin="Chennai", duration_days=3)

    slots = message_parser.parse_deterministic("Yes take it", current_state=session.state)
    assert slots.confirmation_intent is True

    next_state, payload = StateMachine.transition(session, slots)
    # Must advance to travelers, NOT loop back to dates!
    assert next_state == ConversationState.COLLECT_TRAVELERS
    assert session.draft.start_date is not None
    assert session.draft.end_date is not None
    assert "How many people" in payload["text"]


def test_travelers_bare_digit():
    """When bot asks for travelers, '2' must be recognized."""
    slots = message_parser.parse_deterministic("2", current_state=ConversationState.COLLECT_TRAVELERS)
    assert slots.travelers == 2
