import pytest
from datetime import date
from app.schemas.conversation import UserSession, ConversationState
from app.schemas.trip import TripDraft, TransportPref, HotelPref, BudgetLevel, BerthPreference
from app.understanding.message_parser import message_parser
from app.conversation.state_machine import StateMachine
from app.whatsapp.messages import format_itinerary_message
from app.understanding.city_validator import city_validator


@pytest.mark.asyncio
async def test_dual_city_extraction_with_railway_codes():
    """Verify 'i want to go to madurai from rjpm' extracts Madurai and Rajapalayam."""
    slots = await message_parser.parse(
        text="i want to go to madurai from rjpm",
        payload_id=None,
        current_state=ConversationState.START,
    )
    assert slots.destination == "Madurai"
    assert slots.origin == "Rajapalayam"


@pytest.mark.asyncio
async def test_city_alias_validator():
    """Verify city_validator maps railway codes and aliases."""
    is_valid, norm, sugg = await city_validator.validate_city("rjpm")
    assert is_valid is True
    assert norm == "Rajapalayam"

    is_valid, norm, sugg = await city_validator.validate_city("mdu")
    assert is_valid is True
    assert norm == "Madurai"

    # Conversational prefix stripping
    is_valid, norm, sugg = await city_validator.validate_city("I want to go to madurai")
    assert is_valid is True
    assert norm == "Madurai"


@pytest.mark.asyncio
async def test_car_transport_mode_parsing():
    """Verify 'By my own car' or 'own car' extracts TransportPref.car."""
    slots = await message_parser.parse(
        text="By my own car",
        payload_id=None,
        current_state=ConversationState.COLLECT_TRANSPORT,
    )
    assert slots.transport_mode == TransportPref.car

    slots2 = await message_parser.parse(
        text="drive by car",
        payload_id=None,
        current_state=ConversationState.COLLECT_TRANSPORT,
    )
    assert slots2.transport_mode == TransportPref.car


@pytest.mark.asyncio
async def test_cancel_and_exit_global_intent():
    """Verify 'exit' or 'cancel the trip' triggers cancellation and clears session."""
    session = UserSession(
        wa_id="12345",
        user_name="Jashwanth",
        state=ConversationState.COLLECT_TRAIN_CLASS,
        draft=TripDraft(
            origin="Chennai",
            destination="Madurai",
            transport_mode=TransportPref.train,
        ),
    )

    slots = await message_parser.parse(
        text="exit",
        payload_id=None,
        current_state=session.state,
    )
    assert slots.reset_intent is True
    assert slots.cancel_intent is True

    next_state, prompt = StateMachine.transition(session, slots)
    assert next_state == ConversationState.START
    assert session.draft.destination is None
    assert session.draft.origin is None
    assert "cancelled" in prompt["text"].lower()
    assert any("Plan New Trip" in title for _, title in prompt.get("buttons", []))


@pytest.mark.asyncio
async def test_new_trip_intent_returns_welcome():
    """Verify 'new trip' or 'plan new trip' resets session and greets with welcome prompt."""
    session = UserSession(
        wa_id="12345",
        user_name="Jashwanth",
        state=ConversationState.COLLECT_BUDGET,
        draft=TripDraft(origin="Chennai", destination="Goa"),
    )

    slots = await message_parser.parse(
        text="new trip",
        payload_id=None,
        current_state=session.state,
    )
    assert slots.reset_intent is True
    assert slots.cancel_intent is False

    next_state, prompt = StateMachine.transition(session, slots)
    assert next_state == ConversationState.START
    assert session.draft.destination is None
    assert "where is your dream destination" in prompt["text"].lower()


@pytest.mark.asyncio
async def test_car_transition_out_of_train_class():
    """If user is prompted for train class but says 'By my own car', state transitions to hotel."""
    session = UserSession(
        wa_id="12345",
        user_name="Jashwanth",
        state=ConversationState.COLLECT_TRAIN_CLASS,
        draft=TripDraft(
            origin="Rajapalayam",
            destination="Madurai",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 4),
            duration_days=3,
            travelers=2,
            budget_level=BudgetLevel.medium,
            transport_mode=TransportPref.train,
        ),
    )

    slots = await message_parser.parse(
        text="By my own car",
        payload_id=None,
        current_state=session.state,
    )
    assert slots.transport_mode == TransportPref.car

    next_state, prompt = StateMachine.transition(session, slots)
    # Draft should now have car as transport and no berth preference
    assert session.draft.transport_mode == TransportPref.car
    assert session.draft.berth_preference is None
    # Next state should bypass train class and ask for hotel!
    assert next_state == ConversationState.COLLECT_HOTEL
    assert "accommodation" in prompt["text"].lower() or "hotel" in prompt["text"].lower()


def test_itinerary_formatting_with_car():
    """Verify format_itinerary_message renders road trip / self-drive information."""
    itinerary_data = {
        "summary": {
            "days": 3,
            "travelers": 2,
            "budget_level": "medium",
            "pace": "Relaxed",
        },
        "transport_mode": "car",
        "hotel": {
            "name": "Heritage Madurai",
            "price_per_night": 3500,
        },
        "days": [
            {
                "day": 1,
                "date": "2026-11-01",
                "title": "Temple Exploration",
                "schedule": [
                    {"time": "10:00 AM", "activity": "Meenakshi Amman Temple"}
                ]
            }
        ]
    }

    message = format_itinerary_message(
        itinerary=itinerary_data,
        origin="Rajapalayam",
        destination="Madurai",
    )

    assert "TRANSIT & COMMUTE" in message
    assert "Self-Drive / Own Car" in message
    assert "Rajapalayam" in message
    assert "Madurai" in message
