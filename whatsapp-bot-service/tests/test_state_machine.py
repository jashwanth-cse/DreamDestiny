import pytest
from datetime import date
from app.schemas.conversation import UserSession, ConversationState
from app.understanding.schemas import ExtractedTripSlots
from app.conversation.state_machine import StateMachine
from app.schemas.trip import BudgetLevel, TransportPref, HotelPref


def test_state_machine_progressive_transitions():
    """Verify standard turn-by-turn state transitions."""
    session = UserSession(wa_id="919876543210")
    assert session.state == ConversationState.START

    # 1. User specifies destination
    slots1 = ExtractedTripSlots(destination="Goa")
    state1, prompt1 = StateMachine.transition(session, slots1)
    assert state1 == ConversationState.COLLECT_ORIGIN
    assert session.draft.destination == "Goa"

    # 2. User specifies origin
    slots2 = ExtractedTripSlots(origin="Mumbai")
    state2, prompt2 = StateMachine.transition(session, slots2)
    assert state2 == ConversationState.COLLECT_DATES
    assert session.draft.origin == "Mumbai"

    # 3. User specifies dates
    slots3 = ExtractedTripSlots(start_date=date(2026, 11, 1), end_date=date(2026, 11, 5))
    state3, prompt3 = StateMachine.transition(session, slots3)
    assert state3 == ConversationState.COLLECT_TRAVELERS

    # 4. User specifies travelers
    slots4 = ExtractedTripSlots(travelers=2)
    state4, prompt4 = StateMachine.transition(session, slots4)
    assert state4 == ConversationState.COLLECT_BUDGET

    # 5. User specifies budget
    slots5 = ExtractedTripSlots(budget_level=BudgetLevel.medium)
    state5, prompt5 = StateMachine.transition(session, slots5)
    assert state5 == ConversationState.COLLECT_TRANSPORT

    # 6. User specifies transport
    slots6 = ExtractedTripSlots(transport_mode=TransportPref.train)
    state6, prompt6 = StateMachine.transition(session, slots6)
    assert state6 == ConversationState.COLLECT_HOTEL

    # 7. User specifies hotel
    slots7 = ExtractedTripSlots(hotel_category=HotelPref.mid_range)
    state7, prompt7 = StateMachine.transition(session, slots7)
    assert state7 == ConversationState.CONFIRM_TRIP

    # 8. User confirms trip
    slots8 = ExtractedTripSlots(confirmation_intent=True)
    state8, prompt8 = StateMachine.transition(session, slots8)
    assert state8 == ConversationState.GENERATING


def test_state_machine_multi_slot_jump():
    """Verify that providing all slots at once jumps directly to CONFIRM_TRIP."""
    session = UserSession(wa_id="919876543210")
    slots = ExtractedTripSlots(
        origin="Delhi",
        destination="Jaipur",
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 23),
        travelers=4,
        budget_level=BudgetLevel.high,
        transport_mode=TransportPref.flight,
        hotel_category=HotelPref.luxury,
    )

    state, prompt = StateMachine.transition(session, slots)
    assert state == ConversationState.CONFIRM_TRIP
    assert "Jaipur" in prompt["text"]
    assert "Delhi" in prompt["text"]
