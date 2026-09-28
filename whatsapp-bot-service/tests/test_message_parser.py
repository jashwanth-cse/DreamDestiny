import pytest
from datetime import date
from app.understanding.message_parser import message_parser
from app.schemas.trip import BudgetLevel, TransportPref, HotelPref


def test_parser_multi_slot_extraction():
    """Verify multi-slot extraction from a single natural language message."""
    text = "I want to travel from Chennai to Goa on 2026-10-15 for 4 days with 2 people"
    slots = message_parser.parse_deterministic(text)

    assert slots.origin == "Chennai"
    assert slots.destination == "Goa"
    assert slots.start_date == date(2026, 10, 15)
    assert slots.duration_days == 4
    assert slots.end_date == date(2026, 10, 19)
    assert slots.travelers == 2


def test_parser_interactive_buttons():
    """Verify interactive button IDs map to strict enum slots."""
    slots_train = message_parser.parse_deterministic("Train", payload_id="btn_transport_train")
    assert slots_train.transport_mode == TransportPref.train

    slots_budget = message_parser.parse_deterministic("Low", payload_id="btn_budget_low")
    assert slots_budget.budget_level == BudgetLevel.low

    slots_hotel = message_parser.parse_deterministic("Luxury", payload_id="btn_hotel_luxury")
    assert slots_hotel.hotel_category == HotelPref.luxury


def test_parser_reset_intent():
    """Verify reset triggers are detected."""
    assert message_parser.parse_deterministic("restart").reset_intent is True
    assert message_parser.parse_deterministic("new trip").reset_intent is True
    assert message_parser.parse_deterministic("reset").reset_intent is True


def test_parser_confirmation_intent():
    """Verify confirmation triggers."""
    assert message_parser.parse_deterministic("confirm", payload_id="btn_confirm").confirmation_intent is True
    assert message_parser.parse_deterministic("yes").confirmation_intent is True
    assert message_parser.parse_deterministic("cancel", payload_id="btn_cancel").confirmation_intent is False
