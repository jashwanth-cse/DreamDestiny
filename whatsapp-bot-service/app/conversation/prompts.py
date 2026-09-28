"""
Conversational copy, prompts, and interactive button definitions for each state.
Follows Section 4 and 11 of the specification:
- 1-tap quick buttons for dates, travelers, transport (including Bus), budget, and hotel.
- Engaging, professional emoji-rich copy.
"""

from typing import List, Dict, Any
from app.schemas.trip import TripDraft


def get_welcome_message(user_name: str) -> Dict[str, Any]:
    return {
        "text": (
            f"👋 Hello *{user_name}*! Welcome to *Dream Destiny* — your AI travel assistant. ✈️🎒\n\n"
            "I can build a complete personalized day-by-day itinerary with verified transport, "
            "hotels, and attractions with Google Maps links!\n\n"
            "Where is your dream destination? _(e.g., Goa, Mumbai, Manali, Jaipur, Ooty)_"
        )
    }


def get_origin_prompt(destination: str) -> Dict[str, Any]:
    return {
        "text": f"Awesome! A trip to *{destination}* sounds fantastic. 🌴\n\nWhich city will you be traveling *from*?"
    }


def get_destination_prompt() -> Dict[str, Any]:
    return {
        "text": "Where would you like to travel to? _(e.g., Goa, Mumbai, Manali, Jaipur, Ooty, Varanasi)_"
    }


def get_invalid_city_prompt(candidate: str, is_origin: bool = False) -> Dict[str, Any]:
    role = "departure city" if is_origin else "destination"
    return {
        "text": (
            f"🗺️ I couldn't recognize *'{candidate}'* as a valid {role}.\n\n"
            "Could you please check the spelling or specify a valid city or tourist destination?\n"
            "_(e.g., Goa, Mumbai, Jaipur, Manali, Ooty, Chennai, Bangalore)_"
        )
    }


def get_dates_prompt() -> Dict[str, Any]:
    return {
        "text": (
            "📅 *When would you like to travel, and for how many days?*\n\n"
            "Tap a quick calendar option below, or reply with your preferred dates/duration:\n"
            "• _October 15 to 19_\n"
            "• _From October 7 for 4 days_\n"
            "• _Next Friday for 3 days_"
        ),
        "buttons": [
            ("btn_dates_weekend", "This Weekend (3d)"),
            ("btn_dates_next_weekend", "Next Weekend (4d)"),
            ("btn_dates_next_month", "Next Month (5d)"),
        ],
    }


def get_travelers_prompt() -> Dict[str, Any]:
    return {
        "text": "👥 *How many people are traveling on this journey?*",
        "buttons": [
            ("btn_travelers_1", "Solo (1)"),
            ("btn_travelers_2", "Couple (2)"),
            ("btn_travelers_4", "Family / Group (4)"),
        ],
    }


def get_budget_prompt() -> Dict[str, Any]:
    return {
        "text": "💰 *What is your preferred budget level for this journey?*",
        "buttons": [
            ("btn_budget_low", "Economy / Low"),
            ("btn_budget_medium", "Mid-Range"),
            ("btn_budget_high", "Luxury"),
        ],
    }


def get_transport_prompt() -> Dict[str, Any]:
    return {
        "text": (
            "🚆 *How do you prefer to travel between cities?*\n\n"
            "Tap an option below (or reply _'Any'_ for AI best recommendation):"
        ),
        "buttons": [
            ("btn_transport_flight", "✈️ Flight"),
            ("btn_transport_train", "🚆 Train"),
            ("btn_transport_bus", "🚌 Bus"),
        ],
    }


def get_hotel_prompt() -> Dict[str, Any]:
    return {
        "text": "🏨 *What kind of accommodation do you prefer?*",
        "buttons": [
            ("btn_hotel_budget", "Budget / Hostel"),
            ("btn_hotel_mid", "3-Star Hotel"),
            ("btn_hotel_luxury", "Luxury Resort"),
        ],
    }


def get_confirmation_prompt(draft: TripDraft) -> Dict[str, Any]:
    start_str = draft.start_date.isoformat() if draft.start_date else "TBD"
    end_str = draft.end_date.isoformat() if draft.end_date else "TBD"
    travelers_str = str(draft.travelers or 2)
    transport_str = (draft.transport_mode.value if draft.transport_mode else "Any").title()
    budget_str = (draft.budget_level.value if draft.budget_level else "Medium").title()
    hotel_str = (draft.hotel_category.value if draft.hotel_category else "Any").title()
    dur_str = f" ({draft.duration_days} Days)" if draft.duration_days else ""

    summary = (
        "✨ *PLEASE CONFIRM YOUR TRIP DETAILS* ✨\n\n"
        f"📍 *Route:* {draft.origin} ➔ {draft.destination}\n"
        f"📅 *Dates:* {start_str} to {end_str}{dur_str}\n"
        f"👥 *Travelers:* {travelers_str} person(s)\n"
        f"🚆 *Transport:* {transport_str}\n"
        f"🏨 *Stay:* {hotel_str}\n"
        f"💰 *Budget:* {budget_str}\n\n"
        "Shall I generate your full day-by-day itinerary now?"
    )
    return {
        "text": summary,
        "buttons": [
            ("btn_confirm", "✅ Generate Itinerary"),
            ("btn_cancel", "🔄 Change Details"),
        ],
    }


def get_generating_prompt() -> Dict[str, Any]:
    return {
        "text": (
            "⏳ *Crafting your personalized Dream Destiny itinerary...*\n\n"
            "We are querying live routes, checking hotel rates, and finding top-rated "
            "sightseeing spots with Google Maps navigation.\n\n"
            "This will take about 15-20 seconds. Please hold on! ☕🌴"
        )
    }
