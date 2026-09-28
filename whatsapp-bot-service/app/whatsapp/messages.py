"""
Message builders for Meta WhatsApp Cloud API payloads and itinerary formatting.
Follows Section 11 of the specification:
- Reply buttons for small fixed choices (<=3)
- List messages for larger choice sets (<=10)
- Clean, readable WhatsApp itinerary formatting with markdown and emojis
"""

from typing import List, Tuple, Dict, Any, Optional


def build_text_message(recipient: str, text: str) -> Dict[str, Any]:
    """Construct standard WhatsApp text message payload."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }


def build_button_message(
    recipient: str,
    body_text: str,
    buttons: List[Tuple[str, str]],  # List of (button_id, button_title)
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construct WhatsApp Interactive Reply Button message (maximum 3 buttons).
    Button titles must be <= 20 characters as required by Meta.
    """
    btn_objs = []
    for btn_id, title in buttons[:3]:
        btn_objs.append({
            "type": "reply",
            "reply": {
                "id": btn_id[:256],
                "title": title[:20],
            },
        })

    interactive_block: Dict[str, Any] = {
        "type": "button",
        "body": {"text": body_text},
        "action": {"buttons": btn_objs},
    }
    if header_text:
        interactive_block["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_block["footer"] = {"text": footer_text}

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": interactive_block,
    }


def build_list_message(
    recipient: str,
    body_text: str,
    button_label: str,
    sections: List[Dict[str, Any]],
    title_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construct WhatsApp Interactive List message (up to 10 choices).
    sections: [{"title": "...", "rows": [{"id": "...", "title": "...", "description": "..."}]}]
    """
    interactive_block: Dict[str, Any] = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_label[:20],
            "sections": sections,
        },
    }
    if title_text:
        interactive_block["header"] = {"type": "text", "text": title_text[:60]}

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": interactive_block,
    }


def format_itinerary_message(itinerary: Dict[str, Any], origin: str, destination: str) -> str:
    """
    Formats the JSON Itinerary produced by planner-service into a readable,
    visually appealing WhatsApp markdown message.
    """
    lines = []
    trip_title = itinerary.get("trip_title") or f"{origin.title()} to {destination.title()} Journey"
    summary = itinerary.get("summary") or "Here is your AI-curated personalized travel itinerary!"

    lines.append(f"🌴 *{trip_title.upper()}* 🌴")
    lines.append(f"_{summary}_\n")

    # Hotel / Stay
    hotel = itinerary.get("hotel") or itinerary.get("accommodation")
    if hotel and isinstance(hotel, dict):
        h_name = hotel.get("name") or "Recommended Hotel"
        h_rate = hotel.get("rate_per_night") or hotel.get("price") or ""
        h_area = hotel.get("location") or hotel.get("area") or ""
        lines.append("🏨 *ACCOMMODATION:*")
        lines.append(f"• *{h_name}* {f'({h_area})' if h_area else ''}")
        if h_rate:
            lines.append(f"  Price: ~₹{h_rate}/night")
        lines.append("")

    # Transport Outbound
    transport = itinerary.get("transport") or {}
    outbound = transport.get("outbound") if isinstance(transport, dict) else None
    if outbound and isinstance(outbound, dict):
        lines.append("🚆 *TRANSPORT RECOMMENDATION:*")
        mode = outbound.get("mode", "Transport").title()
        name = outbound.get("name") or outbound.get("number") or "Direct Route"
        price = outbound.get("price") or outbound.get("fare") or ""
        lines.append(f"• {mode}: {name} {f'(~₹{price})' if price else ''}")
        lines.append("")

    # Day-by-day plan
    days = itinerary.get("days") or itinerary.get("itinerary") or []
    if days and isinstance(days, list):
        lines.append("📅 *DAY-BY-DAY SCHEDULE:*")
        for i, day in enumerate(days, 1):
            if isinstance(day, dict):
                day_title = day.get("title") or f"Day {day.get('day_number', i)}"
                theme = day.get("theme", "")
                lines.append(f"\n*Day {i}: {day_title}* {f'— _{theme}_' if theme else ''}")
                
                activities = day.get("activities") or day.get("schedule") or []
                for act in activities:
                    if isinstance(act, dict):
                        time_slot = act.get("time") or act.get("slot") or ""
                        act_title = act.get("title") or act.get("activity") or act.get("description") or ""
                        cost = act.get("cost") or act.get("price")
                        cost_str = f" [₹{cost}]" if cost else ""
                        lines.append(f"  • {f'*{time_slot}*: ' if time_slot else ''}{act_title}{cost_str}")
                    elif isinstance(act, str):
                        lines.append(f"  • {act}")
            lines.append("")

    # Budget estimate
    total_cost = itinerary.get("total_estimated_cost") or itinerary.get("estimated_budget")
    if total_cost:
        lines.append(f"💰 *TOTAL ESTIMATED BUDGET:* ₹{total_cost:,}" if isinstance(total_cost, (int, float)) else f"💰 *TOTAL ESTIMATED BUDGET:* {total_cost}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Need any changes?* Just reply:")
    lines.append("• _Make the hotel cheaper_")
    lines.append("• _Change transport to flight_")
    lines.append("• _Add more relaxing activities_")

    return "\n".join(lines)
