"""
Message builders for Meta WhatsApp Cloud API payloads and itinerary formatting.
Follows Section 11 of the specification:
- Reply buttons for small fixed choices (<=3)
- List messages for larger choice sets (<=10)
- Clean, highly readable WhatsApp itinerary formatting with markdown and emojis
- Direct clickable Google Maps navigation links for attractions and accommodation
"""

import urllib.parse
from typing import List, Tuple, Dict, Any, Optional


def build_text_message(recipient: str, text: str) -> Dict[str, Any]:
    """Construct standard WhatsApp text message payload."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {
            "preview_url": True,
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
                "id": str(btn_id)[:256],
                "title": str(title)[:20],
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
    Formats the JSON Itinerary produced by planner-service into a clean,
    visually appealing, executive WhatsApp markdown brochure with clickable Google Maps links.
    Guarantees ZERO raw dictionaries or JSON are emitted into user chat.
    """
    lines = []
    orig_title = origin.strip().title()
    dest_title = destination.strip().title()

    # 1. Header Banner
    lines.append(f"🌴 *{orig_title.upper()} ➔ {dest_title.upper()} EXPEDITION* 🌴")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # 2. Summary details in clean natural language
    summary = itinerary.get("summary")
    if isinstance(summary, dict):
        days = summary.get("days", "")
        travelers = summary.get("travelers", "")
        budget = str(summary.get("budget_level", "")).title()
        pace = str(summary.get("pace", "Moderate")).title()

        info_parts = []
        if days:
            info_parts.append(f"📅 *{days} Days*")
        if travelers:
            info_parts.append(f"👥 *{travelers} Travelers*")
        if budget:
            info_parts.append(f"💰 *{budget} Budget*")
        if pace:
            info_parts.append(f"⚡ *{pace} Pace*")

        lines.append(f"📍 *Route:* {orig_title} ➔ {dest_title}")
        if info_parts:
            lines.append(" • ".join(info_parts))
    else:
        lines.append(f"📍 *Route:* {orig_title} ➔ {dest_title}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # 3. Transport Recommendation (Outbound & Return)
    for t_key, t_label in [("outbound_transport", "Outbound"), ("return_transport", "Return")]:
        transit = itinerary.get(t_key)
        if transit and isinstance(transit, dict):
            mode = transit.get("mode", "Transport").title()
            icon = "✈️" if "Flight" in mode else ("🚆" if "Train" in mode else "🚌")
            
            # Print the header only for outbound, to group them together
            if t_label == "Outbound":
                lines.append(f"{icon} *TRANSIT & COMMUTE:*")
            
            t_name = transit.get("train_name") or transit.get("operator_name") or transit.get("airline") or ""
            # Prioritize flight_number over flight_id to avoid showing fl_xxx hashes
            t_num = transit.get("train_number") or transit.get("flight_number") or transit.get("bus_type") or transit.get("flight_id") or ""
            
            dep_station = transit.get("departure_station") or (orig_title if t_label == "Outbound" else dest_title)
            arr_station = transit.get("arrival_station") or (dest_title if t_label == "Outbound" else orig_title)
            dep_time = transit.get("departure_time") or ""
            arr_time = transit.get("arrival_time") or ""
            fare = transit.get("fare_per_person")
            
            # Seats logic
            seats = transit.get("seats_available")
            seat_status = transit.get("seat_status") or ""
            seats_str = ""
            if seats is not None:
                if str(seats) == "0":
                    seats_str = "WL/Waitlist"
                else:
                    status = f" ({seat_status})" if seat_status else ""
                    seats_str = f"{seats} Seats{status}"

            details = []
            if t_name:
                # Clean up any residual internal IDs in names
                clean_name = t_name.split(" (fl_")[0].split(" (bs_")[0].split(" (tn_")[0]
                clean_num = str(t_num).split(" (fl_")[0] if t_num else ""
                details.append(f"*{clean_name}*" + (f" ({clean_num})" if clean_num else ""))
            if dep_time or arr_time:
                time_str = f"{dep_time} ➔ {arr_time}" if (dep_time and arr_time) else (dep_time or arr_time)
                details.append(f"⏰ {time_str}")
            if fare:
                details.append(f"₹{fare:,}/person")
            if seats_str:
                details.append(f"💺 {seats_str}")

            lines.append(f"• *{t_label} ({mode}):* {', '.join(details) if details else 'Direct route'}")
            if dep_station != (orig_title if t_label == "Outbound" else dest_title) or arr_station != (dest_title if t_label == "Outbound" else orig_title):
                lines.append(f"  _{dep_station} ➔ {arr_station}_")
            if transit.get("instruction"):
                lines.append(f"  💡 {transit['instruction']}")
            lines.append("")

    # 4. Accommodation
    hotel = itinerary.get("hotel") or itinerary.get("accommodation")
    if hotel and isinstance(hotel, dict):
        h_name = hotel.get("hotel_name") or hotel.get("name") or "Recommended Hotel"
        h_price = hotel.get("price_per_night")
        h_total = hotel.get("price_total")
        h_reason = hotel.get("reasoning") or ""

        query = urllib.parse.quote_plus(f"{h_name}, {destination}")
        hotel_map_link = f"https://maps.google.com/?q={query}"

        lines.append("🏨 *HOTEL & STAY:*")
        lines.append(f"• *{h_name}*")
        if h_price:
            price_str = f"~₹{int(h_price):,}/night"
            if h_total:
                price_str += f" (Total: ₹{int(h_total):,})"
            lines.append(f"  💰 Rate: {price_str}")
        lines.append(f"  📍 Map: {hotel_map_link}")
        if h_reason:
            lines.append(f"  _{h_reason}_")
        lines.append("")

    # 5. Day-by-Day Schedule with Clickable Google Maps
    days_list = itinerary.get("days") or itinerary.get("itinerary") or []
    if days_list and isinstance(days_list, list):
        lines.append("📅 *DAY-BY-DAY ITINERARY:*")
        for day in days_list:
            if not isinstance(day, dict):
                continue
            day_num = day.get("day", 1)
            date_str = day.get("date", "")
            theme = day.get("theme", "")

            day_header = f"🗓️ *Day {day_num}*"
            if date_str:
                day_header += f" _({date_str})_"
            if theme:
                day_header += f" — *{theme}*"
            lines.append(f"\n{day_header}")

            acts = day.get("activities") or day.get("schedule") or []
            if not acts:
                lines.append("  • _Free time for leisurely exploration, local dining, and shopping._")
            for act in acts:
                if isinstance(act, dict):
                    name = act.get("attraction_name") or act.get("name") or act.get("title") or act.get("description") or "Sightseeing Spot"
                    start_time = act.get("start_time") or act.get("time") or act.get("slot") or ""
                    dur_min = act.get("duration_minutes")
                    notes = act.get("notes") or ""
                    cost = act.get("estimated_cost") or act.get("cost") or act.get("price")

                    time_prefix = f"[{start_time}] " if start_time else ""
                    if dur_min:
                        time_prefix = f"[{start_time} • {dur_min}m] " if start_time else f"[{dur_min}m] "

                    # Clickable Google Maps link
                    query = urllib.parse.quote_plus(f"{name}, {destination}")
                    place_map_url = f"https://maps.google.com/?q={query}"

                    lines.append(f"  • {time_prefix}*{name}*")
                    lines.append(f"    📍 Maps: {place_map_url}")
                    if notes:
                        lines.append(f"    _{notes}_")
                    if cost and float(cost) > 0:
                        lines.append(f"    🎟️ Entry: ₹{int(float(cost)):,}")
                elif isinstance(act, str) and act.strip():
                    lines.append(f"  • {act.strip()}")
            lines.append("")

    # 6. Budget Breakdown
    cost_info = itinerary.get("cost_breakdown") or {}
    total_cost = itinerary.get("total_cost") or cost_info.get("total_cost") or itinerary.get("total_estimated_cost")
    if total_cost:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 *ESTIMATED TOTAL BUDGET:* ~₹{int(float(total_cost)):,}")
        breakdown_items = []
        if cost_info.get("transport_cost"):
            breakdown_items.append(f"Transit: ₹{int(float(cost_info['transport_cost'])):,}")
        if cost_info.get("hotel_cost"):
            breakdown_items.append(f"Stay: ₹{int(float(cost_info['hotel_cost'])):,}")
        if cost_info.get("activities_estimated_cost"):
            breakdown_items.append(f"Activities: ₹{int(float(cost_info['activities_estimated_cost'])):,}")
        if breakdown_items:
            lines.append(f"• {' | '.join(breakdown_items)}")
        lines.append("")

    # 7. Actionable modification prompts
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Need any changes?* Just reply:")
    lines.append("• _Make the hotel cheaper_")
    lines.append("• _Switch transport to flight / train / bus_")
    lines.append("• _Add more relaxing activities_")
    lines.append("• Or reply _'Menu'_ for options or _'New trip'_ to plan another journey")

    return "\n".join(lines)
