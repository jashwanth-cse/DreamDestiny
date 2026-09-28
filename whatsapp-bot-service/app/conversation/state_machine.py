"""
Deterministic Conversation State Machine.
Follows Section 4 and Section 36 of the specification:
- Enforces strict deterministic transitions.
- Supports multi-field extraction in a single user message.
- Bypasses questions for slots already answered.
- The LLM does not control state transitions.
"""

import logging
from typing import Tuple

from app.schemas.conversation import ConversationState, UserSession
from app.schemas.trip import TripDraft
from app.understanding.schemas import ExtractedTripSlots
from app.conversation import prompts

logger = logging.getLogger(__name__)


class StateMachine:
    @staticmethod
    def apply_slots(draft: TripDraft, slots: ExtractedTripSlots):
        """Update draft in-place with newly extracted slots without overwriting valid data with None."""
        if slots.origin:
            draft.origin = slots.origin
        if slots.destination:
            draft.destination = slots.destination
        if slots.start_date:
            draft.start_date = slots.start_date
        if slots.end_date:
            draft.end_date = slots.end_date
        if slots.duration_days:
            draft.duration_days = slots.duration_days
        if slots.travelers:
            draft.travelers = slots.travelers
        if slots.budget_level:
            draft.budget_level = slots.budget_level
        if slots.transport_mode:
            draft.transport_mode = slots.transport_mode
        if slots.hotel_category:
            draft.hotel_category = slots.hotel_category
        if slots.interests:
            draft.interests = list(set(draft.interests + slots.interests))

    @classmethod
    def get_next_missing_slot_state(cls, draft: TripDraft) -> ConversationState:
        """Determines the next required question based on missing fields in TripDraft."""
        if not draft.destination:
            return ConversationState.COLLECT_DESTINATION
        if not draft.origin:
            return ConversationState.COLLECT_ORIGIN
        if not draft.start_date or not draft.end_date:
            return ConversationState.COLLECT_DATES
        if not draft.travelers:
            return ConversationState.COLLECT_TRAVELERS
        if not draft.budget_level:
            return ConversationState.COLLECT_BUDGET
        if not draft.transport_mode:
            return ConversationState.COLLECT_TRANSPORT
        if not draft.hotel_category:
            return ConversationState.COLLECT_HOTEL

        return ConversationState.CONFIRM_TRIP

    @classmethod
    def transition(cls, session: UserSession, slots: ExtractedTripSlots) -> Tuple[ConversationState, dict]:
        """
        Executes a deterministic state machine transition based on the user's current session state
        and newly extracted slots. Returns (new_state, response_payload).
        """
        # 1. Check for Reset / Cancel
        if slots.reset_intent or slots.confirmation_intent is False:
            session.draft = TripDraft()
            session.state = ConversationState.START
            return ConversationState.START, prompts.get_welcome_message(session.user_name)

        # 2. Apply any extracted slots to draft
        cls.apply_slots(session.draft, slots)

        current = session.state

        # 3. State transitions
        if current in (ConversationState.START, ConversationState.COLLECT_DESTINATION, ConversationState.COLLECT_ORIGIN):
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.COLLECT_DATES:
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.COLLECT_TRAVELERS:
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.COLLECT_BUDGET:
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.COLLECT_TRANSPORT:
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.COLLECT_HOTEL:
            next_state = cls.get_next_missing_slot_state(session.draft)
            session.state = next_state
            return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

        elif current == ConversationState.CONFIRM_TRIP:
            if slots.confirmation_intent is True:
                session.state = ConversationState.GENERATING
                return ConversationState.GENERATING, prompts.get_generating_prompt()
            else:
                return ConversationState.CONFIRM_TRIP, prompts.get_confirmation_prompt(session.draft)

        elif current == ConversationState.COMPLETED:
            if slots.modification_intent:
                session.state = ConversationState.MODIFYING
                return ConversationState.MODIFYING, {
                    "text": f"Got it! Modifying your itinerary with: *{slots.modification_intent}* 🔄\nPlease hold on..."
                }
            # If user types something new after completion, check if it's a new trip request
            if slots.destination or slots.origin:
                session.draft = TripDraft()
                cls.apply_slots(session.draft, slots)
                next_state = cls.get_next_missing_slot_state(session.draft)
                session.state = next_state
                return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

            return ConversationState.COMPLETED, {
                "text": "Your itinerary is ready above! You can ask for modifications (e.g. _'Make the hotel cheaper'_ or _'Switch to flight'_) or reply _'New trip'_ to plan another journey."
            }

        elif current == ConversationState.MODIFYING:
            # Transition handled by TripService
            pass

        # Fallback: re-evaluate missing slot
        next_state = cls.get_next_missing_slot_state(session.draft)
        session.state = next_state
        return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

    @classmethod
    def _get_prompt_for_state(cls, state: ConversationState, draft: TripDraft, user_name: str) -> dict:
        if state == ConversationState.START:
            return prompts.get_welcome_message(user_name)
        elif state == ConversationState.COLLECT_DESTINATION:
            return prompts.get_destination_prompt()
        elif state == ConversationState.COLLECT_ORIGIN:
            return prompts.get_origin_prompt(draft.destination or "your destination")
        elif state == ConversationState.COLLECT_DATES:
            return prompts.get_dates_prompt()
        elif state == ConversationState.COLLECT_TRAVELERS:
            return prompts.get_travelers_prompt()
        elif state == ConversationState.COLLECT_BUDGET:
            return prompts.get_budget_prompt()
        elif state == ConversationState.COLLECT_TRANSPORT:
            return prompts.get_transport_prompt()
        elif state == ConversationState.COLLECT_HOTEL:
            return prompts.get_hotel_prompt()
        elif state == ConversationState.CONFIRM_TRIP:
            return prompts.get_confirmation_prompt(draft)
        elif state == ConversationState.GENERATING:
            return prompts.get_generating_prompt()
        return prompts.get_welcome_message(user_name)
