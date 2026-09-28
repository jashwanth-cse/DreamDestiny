"""
Conversational copy, prompts, and interactive button definitions for each state.
Follows Section 4 and 11 of the specification.
"""

from typing import Tuple, List, Dict, Any
from app.schemas.trip import TripDraft


def get_welcome_message(user_name: str) -> Dict[str, Any]:
    return {
        "text": (
            f"👋 Hello *{user_name}*! Welcome to *Dream Destiny* — your AI travel assistant.\n\n"
            "I can help you build an end-to-end trip itinerary complete with transport, hotels, "
            "and daily sightseeing activities.\n\n"
            "Where would you like to travel to? _(e.g., Goa, Manali, Jaipur)_"
        )
    }


def get_origin_prompt(destination: str) -> Dict[str, Any]:
    return {
        "text": f"Awesome! A trip to *{destination}* sounds fantastic. 🌴\n\nWhich city will you be traveling *from*?"
    }


def get_destination_prompt() -> Dict[str, Any]:
    return {
        "text": "Where is your dream destination? _(e.g., Ooty, Varanasi, Mumbai)_"
    }


def get_dates_prompt() -> Dict[str, Any]:
    return {
        "text": (
            "📅 When are you planning to travel, and for how many days?\n\n"
            "You can reply with dates like:\n"
            "• _2026-10-15 for 4 days_\n"
            "• _15-10-2026 to 19-10-2026_"
        )
    }


def get_travelers_prompt() -> Dict[str, Any]:
    return {
        "text": "👥 How many people are traveling on this trip?",
        "buttons": [
            ("btn_travelers_1", "Solo (1)"),
            ("btn_travelers_2", "Couple (2)"),
            ("btn_travelers_4", "Family / Group (4)"),
        ],
    }


def get_budget_prompt() -> Dict[str, Any]:
    return {
        "text": "💰 What is your preferred budget level for this journey?",
        "buttons": [
            ("btn_budget_low", "Economy / Low"),
            ("btn_budget_medium", "Mid-Range"),
            ("btn_budget_high", "Luxury"),
        ],
    }


def get_transport_prompt() -> Dict[str, Any]:
    return {
        "text": "🚆 How do you prefer to travel between cities?",
        "buttons": [
            ("btn_transport_train", "Train"),
            ("btn_transport_flight", "Flight"),
            ("btn_transport_any", "Any / Best Route"),
        ],
    }


def get_hotel_prompt() -> Dict[str, Any]:
    return {
        "text": "🏨 What kind of stay do you prefer?",
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

    summary = (
        "✨ *PLEASE CONFIRM YOUR TRIP DETAILS* ✨\n\n"
        f"📍 *Route:* {draft.origin} ➔ {draft.destination}\n"
        f"📅 *Dates:* {start_str} to {end_str}\n"
        f"👥 *Travelers:* {travelers_str} person(s)\n"
        f"🚆 *Transport:* {transport_str}\n"
        f"💰 *Budget:* {budget_str}\n"
        f"🏨 *Hotel:* {hotel_str}\n\n"
        "Shall I go ahead and generate your complete itinerary?"
    )

    return {
        "text": summary,
        "buttons": [
            ("btn_confirm", "✅ Confirm & Plan"),
            ("btn_cancel", "❌ Start Over"),
        ],
    }


def get_generating_prompt() -> Dict[str, Any]:
    return {
        "text": (
            "🚀 *Generating your personalized itinerary...*\n\n"
            "Our AI is coordinating live transport routes, querying available hotels, "
            "and curating day-by-day sightseeing attractions.\n\n"
            "This will take about 15–30 seconds. Please hold on! ⏳"
        )
    }
