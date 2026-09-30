"""
Conversational copy, prompts, and interactive button definitions for each state.
Follows Section 4 and 11 of the specification:
- Clean, executive WhatsApp formatting with proper UTF-8 emojis.
- 1-tap quick buttons for dates, travelers, transport (including Bus), budget, and hotel.
- Centralized main menu, resumption prompt for paused conversations, and past itineraries browser.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from app.schemas.trip import TripDraft


def get_welcome_message(user_name: str = "Traveler") -> Dict[str, Any]:
    return {
        "text": (
            f"👋 Hello *{user_name}*! Welcome to *Dream Destiny* — your AI travel concierge. 🌴✨\n\n"
            "I can build a complete, personalized day-by-day itinerary with verified transport, "
            "hotels, and attractions with direct Google Maps links!\n\n"
            "Where is your dream destination? _(e.g., Goa, Mumbai, Manali, Jaipur, Ooty)_"
        )
    }


def get_resumption_prompt(user_name: str, draft: Optional[TripDraft] = None, is_completed: bool = False) -> Dict[str, Any]:
    """
    Prompt shown when a user returns after a conversation pause or on a new day.
    Provides clear choices: resume last plan, start a new trip, or open the menu.
    """
    dest = draft.destination if draft and draft.destination else "your previous destination"
    
    if is_completed:
        body = (
            f"🌟 *Welcome back, {user_name}!* 🌟\n\n"
            f"Your latest itinerary to *{dest}* is safely saved in your account.\n\n"
            "Would you like to review/modify that trip, or plan a brand new journey?"
        )
        buttons = [
            ("btn_resume_trip", "🔄 Review Trip"),
            ("btn_start_over", "🚀 Plan New Trip"),
            ("btn_menu", "📋 Main Menu"),
        ]
    else:
        # Paused mid-planning
        orig = f" from *{draft.origin}*" if draft and draft.origin else ""
        body = (
            f"🌟 *Welcome back, {user_name}!* 🌟\n\n"
            f"You were planning a trip to *{dest}*{orig}.\n\n"
            "Would you like to pick up where we left off, or start fresh?"
        )
        buttons = [
            ("btn_resume_trip", "🔄 Continue Trip"),
            ("btn_start_over", "🚀 Start Over"),
            ("btn_menu", "📋 Main Menu"),
        ]
    
    return {
        "text": body,
        "buttons": buttons,
    }


def get_main_menu_prompt(has_active_plan: bool = False, active_dest: Optional[str] = None) -> Dict[str, Any]:
    """Centralized Menu prompt for navigation."""
    active_line = f"\n🔄 *Active Plan:* Trip to {active_dest}\n" if (has_active_plan and active_dest) else ""
    text = (
        "🌟 *DREAM DESTINY TRAVEL CONCIERGE* 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "How can I assist your travels today?\n"
        f"{active_line}\n"
        "1️⃣ ✈️ *Plan a New Trip*\n"
        "2️⃣ 📜 *My Saved Itineraries*\n"
        "3️⃣ 🔄 *Resume Current Plan*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Tap a button below or type your choice:"
    )
    buttons = [
        ("btn_plan_new", "✈️ Plan New Trip"),
        ("btn_past_trips", "📜 My Saved Trips"),
    ]
    if has_active_plan:
        buttons.append(("btn_resume_trip", "🔄 Resume Plan"))
    else:
        buttons.append(("btn_start_over", "🚀 Start Fresh"))
    
    return {"text": text, "buttons": buttons}


def get_past_trips_prompt(trips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Formats list of saved past itineraries for user review."""
    if not trips:
        return {
            "text": (
                "📜 *YOUR SAVED ITINERARIES*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "You don't have any saved itineraries yet.\n\n"
                "Ready to plan your first dream vacation? 🌴"
            ),
            "buttons": [
                ("btn_plan_new", "✈️ Plan New Trip"),
                ("btn_menu", "📋 Main Menu"),
            ],
        }

    lines = [
        "📜 *YOUR SAVED ITINERARIES*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    buttons = []
    
    for idx, trip in enumerate(trips[:3], 1):
        orig = trip.get("origin", "Origin").title()
        dest = trip.get("destination", "Destination").title()
        days = trip.get("days", "")
        days_str = f" ({days} Days)" if days else ""
        created = trip.get("created_at", "")
        date_str = ""
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                date_str = f" • _{dt.strftime('%d %b %Y')}_"
            except Exception:
                pass
        
        lines.append(f"*{idx}. {dest}*{days_str}{date_str}")
        lines.append(f"   Route: {orig} ➔ {dest}")
        lines.append("")
        buttons.append((f"btn_trip_{idx}", f"Trip {idx}: {dest[:10]}"))

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Reply with the Trip Number* (e.g. _'Trip 1'_) to view details, or tap below:")
    
    # WhatsApp allows max 3 buttons
    action_buttons = buttons[:2]
    action_buttons.append(("btn_menu", "📋 Main Menu"))

    return {
        "text": "\n".join(lines),
        "buttons": action_buttons,
    }


def get_origin_prompt(destination: str) -> Dict[str, Any]:
    return {
        "text": f"Awesome! A trip to *{destination}* sounds fantastic. 🌴\n\nWhich city will you be traveling *from*?"
    }


def get_destination_prompt() -> Dict[str, Any]:
    return {
        "text": "Where would you like to travel to? 🌴\n_(e.g., Goa, Mumbai, Manali, Jaipur, Ooty, Varanasi)_"
    }


def get_invalid_city_prompt(candidate: str, is_origin: bool = False, suggested_city: Optional[str] = None) -> Dict[str, Any]:
    role = "departure city" if is_origin else "destination"
    if suggested_city:
        return {
            "text": f"🤔 I couldn't recognize *'{candidate}'*.\n\nDid you mean *{suggested_city}*?",
            "buttons": [
                (f"btn_typo_yes_{suggested_city[:15]}", f"✅ Yes, {suggested_city[:12]}"),
                ("btn_typo_no", "❌ No, let me retype"),
            ]
        }
    return {
        "text": (
            f"🤔 I couldn't recognize *'{candidate}'* as a valid {role}.\n\n"
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


def get_train_class_prompt() -> Dict[str, Any]:
    return {
        "text": "🚆 *Which train class do you prefer?*",
        "buttons": [
            ("btn_train_3a", "3AC"),
            ("btn_train_2a", "2AC"),
            ("btn_train_sl", "Sleeper (SL)"),
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
        "📋 *PLEASE CONFIRM YOUR TRIP DETAILS* 📋\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Route:* {draft.origin} ➔ {draft.destination}\n"
        f"📅 *Dates:* {start_str} to {end_str}{dur_str}\n"
        f"👥 *Travelers:* {travelers_str} person(s)\n"
        f"🚗 *Transport:* {transport_str}\n"
        f"🏨 *Stay:* {hotel_str}\n"
        f"💰 *Budget:* {budget_str}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
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
            "⚡ *Crafting your personalized Dream Destiny itinerary...*\n\n"
            "We are querying live routes, checking hotel rates, and finding top-rated "
            "sightseeing spots with Google Maps navigation.\n\n"
            "This will take about 15-20 seconds. Please hold on! 🌴"
        )
    }
