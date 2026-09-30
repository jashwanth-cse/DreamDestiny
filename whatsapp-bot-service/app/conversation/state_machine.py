"""
Deterministic Conversation State Machine with Intelligent Context-Aware Fallbacks.
Follows Section 4 and Section 36 of the specification:
- Enforces strict deterministic transitions.
- Supports multi-field extraction in a single user message.
- Bypasses questions for slots already answered.
- Handles natural affirmations ("yes", "take it", "ok") without looping.
- Automatically calculates missing dates/durations using sensible smart defaults.
- Manages Resumption Choices, Centralized Main Menu, and Saved Trips.
"""

import logging
from datetime import date, timedelta
from typing import Tuple

from app.schemas.conversation import ConversationState, UserSession
from app.schemas.trip import TripDraft, BudgetLevel, TransportPref, HotelPref
from app.understanding.schemas import ExtractedTripSlots
from app.conversation import prompts

logger = logging.getLogger(__name__)


class StateMachine:
    @staticmethod
    def apply_slots(draft: TripDraft, slots: ExtractedTripSlots):
        """Update draft in-place with newly extracted slots and reconcile dates."""
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
        if slots.train_class:
            # Map slots.train_class string to BerthPreference
            from app.schemas.trip import BerthPreference
            try:
                draft.berth_preference = BerthPreference(slots.train_class)
            except ValueError:
                # Fallback to any if invalid class
                draft.berth_preference = BerthPreference.any
        if slots.hotel_category:
            draft.hotel_category = slots.hotel_category
        if slots.interests:
            draft.interests = list(set(draft.interests + slots.interests))

        # Reconcile dates and duration automatically
        if draft.start_date and draft.end_date:
            draft.duration_days = max(1, (draft.end_date - draft.start_date).days)
        elif draft.start_date and draft.duration_days and not draft.end_date:
            draft.end_date = draft.start_date + timedelta(days=draft.duration_days)
        elif draft.end_date and draft.duration_days and not draft.start_date:
            draft.start_date = draft.end_date - timedelta(days=draft.duration_days)

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
        if draft.transport_mode == TransportPref.train and not draft.berth_preference:
            return ConversationState.COLLECT_TRAIN_CLASS
        if not draft.hotel_category:
            return ConversationState.COLLECT_HOTEL

        return ConversationState.CONFIRM_TRIP

    @classmethod
    def transition(cls, session: UserSession, slots: ExtractedTripSlots) -> Tuple[ConversationState, dict]:
        """
        Executes a deterministic state machine transition based on the user's current session state
        and newly extracted slots. Never loops indefinitely on conversational affirmations.
        """
        # 1. Check for Invalid City input
        if slots.invalid_city:
            if slots.suggested_city:
                session.paused_state = session.state  # remember where we were
                session.state = ConversationState.CONFIRM_CITY_TYPO
            return session.state, prompts.get_invalid_city_prompt(slots.invalid_city, is_origin=slots.is_origin_invalid, suggested_city=slots.suggested_city)

        # 1.b Check for Invalid Dates (ARP violation)
        if slots.invalid_date_reason:
            session.draft.start_date = None
            session.draft.end_date = None
            return ConversationState.COLLECT_DATES, {
                "text": f"⚠️ {slots.invalid_date_reason}\n\n📅 When would you like to travel instead?"
            }

        # 2. Check for Global Main Menu Request
        if slots.menu_intent:
            if session.state not in (ConversationState.MAIN_MENU, ConversationState.RESUME_CHOICE):
                session.paused_state = session.state
            session.state = ConversationState.MAIN_MENU
            has_plan = bool(session.draft.destination or session.current_trip_id)
            return ConversationState.MAIN_MENU, prompts.get_main_menu_prompt(has_plan, session.draft.destination)

        # 3. Check for Reset / Cancel / Plan New Trip
        if slots.reset_intent or (slots.confirmation_intent is False and session.state == ConversationState.CONFIRM_TRIP):
            session.draft = TripDraft()
            session.current_trip_id = None
            session.paused_state = None
            session.state = ConversationState.START
            return ConversationState.START, prompts.get_welcome_message(session.user_name)

        # 4. Check for Resumption / Continue Intent
        if slots.resume_intent or (session.state == ConversationState.RESUME_CHOICE and slots.confirmation_intent):
            target_state = session.paused_state
            if target_state and target_state not in (ConversationState.RESUME_CHOICE, ConversationState.MAIN_MENU):
                session.state = target_state
                session.paused_state = None
                if target_state == ConversationState.COMPLETED:
                    dest = session.draft.destination or "your trip"
                    return ConversationState.COMPLETED, {
                        "text": f"🌴 Resuming your plan to *{dest}*! What modifications would you like? (e.g. _'Make hotel cheaper'_ or _'Switch to flight'_)"
                    }
                return target_state, cls._get_prompt_for_state(target_state, session.draft, session.user_name)
            elif session.draft.destination:
                next_state = cls.get_next_missing_slot_state(session.draft)
                session.state = next_state
                return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)
            else:
                session.state = ConversationState.COLLECT_DESTINATION
                return ConversationState.COLLECT_DESTINATION, prompts.get_destination_prompt()

        # 5. If currently in RESUME_CHOICE and user typed new destination
        if session.state == ConversationState.RESUME_CHOICE:
            if slots.destination or slots.origin:
                session.draft = TripDraft()
                session.paused_state = None
                cls.apply_slots(session.draft, slots)
                next_state = cls.get_next_missing_slot_state(session.draft)
                session.state = next_state
                return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)
            is_comp = (session.paused_state == ConversationState.COMPLETED)
            return ConversationState.RESUME_CHOICE, prompts.get_resumption_prompt(session.user_name, session.draft, is_completed=is_comp)
            
        # 5.b Handle City Typo Confirmation
        if session.state == ConversationState.CONFIRM_CITY_TYPO:
            if slots.confirmation_intent is True or (hasattr(slots, 'typo_confirmed_city') and slots.typo_confirmed_city):
                city_to_set = getattr(slots, 'typo_confirmed_city', None) or slots.destination or slots.origin
                if session.paused_state == ConversationState.COLLECT_ORIGIN:
                    session.draft.origin = city_to_set
                else:
                    session.draft.destination = city_to_set
                session.state = session.paused_state
                session.paused_state = None
                next_state = cls.get_next_missing_slot_state(session.draft)
                session.state = next_state
                return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)
            elif slots.confirmation_intent is False:
                session.state = session.paused_state
                session.paused_state = None
                return session.state, cls._get_prompt_for_state(session.state, session.draft, session.user_name)
                
        # 5.c Handle Waitlist RAC Response
        if session.state == ConversationState.HANDLE_WAITLIST_RAC:
            if slots.modification_intent == "change_transport" or slots.confirmation_intent is False:
                session.draft.transport_mode = None
                session.draft.berth_preference = None
                session.state = ConversationState.COLLECT_TRANSPORT
                return session.state, cls._get_prompt_for_state(session.state, session.draft, session.user_name)
            elif slots.confirmation_intent is True:
                # proceed to next state (hotel or confirm)
                session.state = ConversationState.COLLECT_TRAIN_CLASS  # mock old state to transition past it
                pass # let it fall through to step 6 to calculate next state
                
        # 6. Apply extracted slots to draft
        cls.apply_slots(session.draft, slots)

        current = session.state

        # 7. Contextual smart handling for affirmative / single-step replies per state
        if current == ConversationState.COLLECT_DATES:
            if slots.confirmation_intent or (session.draft.duration_days and not session.draft.start_date):
                today = date.today()
                dur = session.draft.duration_days or 3
                days_ahead = (4 - today.weekday()) % 7  # Upcoming Friday
                if days_ahead < 2:
                    days_ahead += 7
                session.draft.start_date = today + timedelta(days=days_ahead)
                session.draft.end_date = session.draft.start_date + timedelta(days=dur)
                session.draft.duration_days = dur
            elif session.draft.start_date and not session.draft.end_date:
                dur = session.draft.duration_days or 3
                session.draft.end_date = session.draft.start_date + timedelta(days=dur)
                session.draft.duration_days = dur

        elif current == ConversationState.COLLECT_TRAVELERS:
            if slots.confirmation_intent and not session.draft.travelers:
                session.draft.travelers = 2  # Smart default: couple

        elif current == ConversationState.COLLECT_BUDGET:
            if slots.confirmation_intent and not session.draft.budget_level:
                session.draft.budget_level = BudgetLevel.medium

        elif current == ConversationState.COLLECT_TRANSPORT:
            if slots.confirmation_intent and not session.draft.transport_mode:
                session.draft.transport_mode = TransportPref.any

        elif current == ConversationState.COLLECT_HOTEL:
            if slots.confirmation_intent and not session.draft.hotel_category:
                session.draft.hotel_category = HotelPref.mid_range

        # 8. State transitions
        if current in (
            ConversationState.START,
            ConversationState.COLLECT_DESTINATION,
            ConversationState.COLLECT_ORIGIN,
            ConversationState.COLLECT_DATES,
            ConversationState.COLLECT_TRAVELERS,
            ConversationState.COLLECT_BUDGET,
            ConversationState.COLLECT_TRANSPORT,
            ConversationState.COLLECT_HOTEL,
            ConversationState.MAIN_MENU,
        ):
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
                    "text": f"Got it! Modifying your itinerary with: *{slots.modification_intent}* 🌴\nPlease hold on..."
                }
            # If user types something new after completion, start fresh journey
            if slots.destination or slots.origin:
                session.draft = TripDraft()
                cls.apply_slots(session.draft, slots)
                next_state = cls.get_next_missing_slot_state(session.draft)
                session.state = next_state
                return next_state, cls._get_prompt_for_state(next_state, session.draft, session.user_name)

            return ConversationState.COMPLETED, {
                "text": (
                    "Your itinerary is ready above! 🌴\n\n"
                    "Would you like to modify it (e.g. _'Make hotel cheaper'_ or _'Switch to flight'_), "
                    "view your saved trips, or plan a new journey?"
                ),
                "buttons": [
                    ("btn_plan_new", "✈️ Plan New Trip"),
                    ("btn_past_trips", "📜 My Trips"),
                    ("btn_menu", "📋 Main Menu"),
                ],
            }

        elif current == ConversationState.MODIFYING:
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
        elif state == ConversationState.COLLECT_TRAIN_CLASS:
            return prompts.get_train_class_prompt()
        elif state == ConversationState.COLLECT_HOTEL:
            return prompts.get_hotel_prompt()
        elif state == ConversationState.CONFIRM_TRIP:
            return prompts.get_confirmation_prompt(draft)
        elif state == ConversationState.GENERATING:
            return prompts.get_generating_prompt()
        elif state == ConversationState.MAIN_MENU:
            return prompts.get_main_menu_prompt(bool(draft.destination), draft.destination)
        elif state == ConversationState.RESUME_CHOICE:
            return prompts.get_resumption_prompt(user_name, draft)
        return prompts.get_welcome_message(user_name)
