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


def test_transport_prompt_includes_bus():
    """Verify Bus is an available button option for transport."""
    from app.conversation import prompts
    p = prompts.get_transport_prompt()
    button_titles = [b[1] for b in p["buttons"]]
    assert any("Bus" in t for t in button_titles)
    assert any("Flight" in t for t in button_titles)
    assert any("Train" in t for t in button_titles)


def test_itinerary_formatting_maps_and_no_raw_dicts():
    """Verify that formatted itinerary has Google Maps links and no raw dicts or empty bullets."""
    from app.whatsapp.messages import format_itinerary_message

    sample_itinerary = {
        "summary": {
            "destination": "Mumbai",
            "origin": "Rajapalayam",
            "days": 3,
            "travelers": 2,
            "pace": "moderate",
            "budget_level": "medium",
        },
        "hotel": {
            "hotel_name": "Taj Mahal Palace",
            "price_per_night": 4500.0,
            "price_total": 9000.0,
            "reasoning": "Heritage sea view hotel",
        },
        "outbound_transport": {
            "mode": "train",
            "train_name": "Pandian Express",
            "train_number": "12638",
            "fare_per_person": 1250,
        },
        "days": [
            {
                "day": 1,
                "date": "2026-10-15",
                "theme": "South Mumbai Exploration",
                "activities": [
                    {
                        "attraction_name": "Gateway of India",
                        "start_time": "10:00",
                        "duration_minutes": 60,
                        "notes": "Historical colonial monument",
                    }
                ],
            }
        ],
        "total_cost": 15000.0,
    }

    formatted = format_itinerary_message(sample_itinerary, "Rajapalayam", "Mumbai")

    # Assert no raw python dict
    assert "{'destination'" not in formatted
    # Assert attraction name is present
    assert "Gateway of India" in formatted
    # Assert Google Maps link is generated
    assert "https://maps.google.com/?q=" in formatted
    # Assert hotel is rendered properly
    assert "Taj Mahal Palace" in formatted
    assert "₹4,500/night" in formatted
    # Assert transport is rendered
    assert "Pandian Express" in formatted


@pytest.mark.asyncio
async def test_city_validation_rejects_irrelevant_names():
    """Verify that irrelevant phrases like 'Check If It Works' are rejected."""
    from app.understanding.city_validator import city_validator
    is_valid, name = await city_validator.validate_city("Check If It Works")
    assert is_valid is False

    is_valid_real, real_name = await city_validator.validate_city("Mumbai")
    assert is_valid_real is True
    assert real_name == "Mumbai"

