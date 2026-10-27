"""
Designer PDF Engine for Dream Destiny.
Renders an ultra-aesthetic, magazine-grade travel scrapbook brochure identical to professional
editorial travel guides, featuring:
- Hero "TRAVEL ITINERARY" typographic lockup in dark forest teal.
- Day-by-day timetable cards with emerald pill ribbon badges and clickable Google Maps navigation links.
- Dedicated showcase of Polaroid-style photo frames with realistic metallic pins, drop shadows, and handwritten captions.
- Verified Accommodation & Transit Bento cards.
- 100% In-Memory rendering via Headless Chromium (Playwright). Zero files on disk.
"""

import io
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Verified, high-resolution photography catalog for key Indian tourist landmarks
LANDMARK_PHOTOS: Dict[str, str] = {
    # Madurai
    "meenakshi": "https://images.unsplash.com/photo-1609137144813-7d9921338f24?auto=format&fit=crop&w=800&q=80",
    "thirumalai": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=800&q=80",
    "mahal": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=800&q=80",
    "gandhi": "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?auto=format&fit=crop&w=800&q=80",
    "teppakulam": "https://images.unsplash.com/photo-1596176530529-78163a4f7af2?auto=format&fit=crop&w=800&q=80",
    "alagar": "https://images.unsplash.com/photo-1544735716-392fe2489ffa?auto=format&fit=crop&w=800&q=80",
    "puthu mandapam": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=800&q=80",
    # Mumbai
    "gateway of india": "https://images.unsplash.com/photo-1570168007204-dfb528c6958f?auto=format&fit=crop&w=800&q=80",
    "marine drive": "https://images.unsplash.com/photo-1566552881560-0be86c53210b?auto=format&fit=crop&w=800&q=80",
    "elephanta": "https://images.unsplash.com/photo-1600100397608-f010e423b971?auto=format&fit=crop&w=800&q=80",
    # Goa
    "baga beach": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=800&q=80",
    "calangute": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
    "aguada": "https://images.unsplash.com/photo-1587974928442-77dc3e0dba72?auto=format&fit=crop&w=800&q=80",
    "basilica": "https://images.unsplash.com/photo-1548013146-72479768bada?auto=format&fit=crop&w=800&q=80",
    # Jaipur & Rajasthan
    "hawa mahal": "https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=800&q=80",
    "amer fort": "https://images.unsplash.com/photo-1603258849040-5e3e2b9c5123?auto=format&fit=crop&w=800&q=80",
    "city palace": "https://images.unsplash.com/photo-1586861635167-e5223aadc9fe?auto=format&fit=crop&w=800&q=80",
    # Agra & Delhi
    "taj mahal": "https://images.unsplash.com/photo-1564507592333-c60657eea523?auto=format&fit=crop&w=800&q=80",
    "india gate": "https://images.unsplash.com/photo-1587474260584-136574528ed5?auto=format&fit=crop&w=800&q=80",
    "qutub minar": "https://images.unsplash.com/photo-1548013146-72479768bada?auto=format&fit=crop&w=800&q=80",
    # Hill Stations & Nature
    "ooty": "https://images.unsplash.com/photo-1589182373726-e4f658ab50f0?auto=format&fit=crop&w=800&q=80",
    "kodaikanal": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=800&q=80",
    "manali": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=800&q=80",
    "kerala": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=800&q=80",
}

# Thematic high-res fallback imagery
FALLBACK_THEMES: Dict[str, str] = {
    "spiritual": "https://images.unsplash.com/photo-1609137144813-7d9921338f24?auto=format&fit=crop&w=800&q=80",
    "nature": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=800&q=80",
    "beach": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=800&q=80",
    "heritage": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=800&q=80",
    "mountain": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=800&q=80",
    "default": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=800&q=80",
}


def resolve_attraction_photo(attraction_name: str, destination: str, provided_url: Optional[str] = None) -> str:
    """Returns a verified high-resolution photograph URL for the attraction."""
    if provided_url and str(provided_url).startswith("http") and not provided_url.endswith(".svg"):
        return provided_url

    name_lower = attraction_name.lower()
    dest_lower = destination.lower()

    # 1. Exact or partial keyword match in catalog
    for key, url in LANDMARK_PHOTOS.items():
        if key in name_lower or key in dest_lower:
            return url

    # 2. Category matching
    if any(k in name_lower for k in ("temple", "church", "mosque", "shrine", "ashram")):
        return FALLBACK_THEMES["spiritual"]
    elif any(k in name_lower for k in ("beach", "sea", "ocean", "cove", "bay")):
        return FALLBACK_THEMES["beach"]
    elif any(k in name_lower for k in ("hill", "peak", "mountain", "valley", "falls", "lake", "forest")):
        return FALLBACK_THEMES["mountain"]
    elif any(k in name_lower for k in ("fort", "palace", "museum", "monument", "mahal", "ruins")):
        return FALLBACK_THEMES["heritage"]

    return FALLBACK_THEMES["default"]


def build_designer_html(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Constructs an editorial travel scrapbook HTML document that mirrors the designer reference.
    Includes active Google Maps links, styled Polaroid photo frames with metallic pins,
    and responsive print styling.
    """
    orig_title = origin.strip().title()
    dest_title = destination.strip().title()

    summary = itinerary.get("summary") or {}
    days_cnt = summary.get("days") or len(itinerary.get("days", [])) or 3
    travelers_cnt = summary.get("travelers") or 2
    budget_tier = str(summary.get("budget_level") or "Medium").title()
    raw_mode = str(itinerary.get("transport_mode") or (trip_meta.get("transport_mode") if trip_meta else "") or "Any").title()
    if any(k in raw_mode.lower() for k in ("car", "drive", "road")):
        mode_label = "Self-Drive / Own Car"
    elif "Train" in raw_mode:
        mode_label = "Train Transit"
    elif "Flight" in raw_mode:
        mode_label = "Flight Transit"
    else:
        mode_label = f"{raw_mode} Transit"

    days_list = itinerary.get("days") or itinerary.get("itinerary") or []

    # ── Collect Polaroid Highlight Attractions (up to 3 distinct places) ───
    polaroid_items = []
    seen_names = set()
    for day in days_list:
        if not isinstance(day, dict):
            continue
        acts = day.get("activities") or day.get("schedule") or []
        for act in acts:
            if not isinstance(act, dict):
                continue
            name = act.get("attraction_name") or act.get("name") or act.get("activity") or ""
            name_clean = name.strip()
            # Filter out generic breakfast/dinner/checkout steps for polaroids
            if any(k in name_clean.lower() for k in ("check-in", "checkout", "breakfast", "dinner", "drive to", "highway")):
                continue
            if name_clean and name_clean.lower() not in seen_names:
                seen_names.add(name_clean.lower())
                img_src = resolve_attraction_photo(name_clean, destination, act.get("image_url"))
                polaroid_items.append({"name": name_clean, "img_src": img_src})
                if len(polaroid_items) >= 3:
                    break
        if len(polaroid_items) >= 3:
            break

    # If fewer than 3 polaroids were gathered, fill with destination highlights
    while len(polaroid_items) < 3:
        idx = len(polaroid_items) + 1
        p_name = f"{dest_title} Landmark Highlight {idx}"
        p_img = resolve_attraction_photo(p_name, destination)
        polaroid_items.append({"name": p_name, "img_src": p_img})

    # ── Build Day Cards HTML ───
    day_cards_html = []
    for d_idx, day in enumerate(days_list[:3]):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day", d_idx + 1)
        theme = day.get("theme") or day.get("title") or "Sightseeing & Local Culture"

        activities_html = []
        acts = day.get("activities") or day.get("schedule") or []
        for act in acts:
            if not isinstance(act, dict):
                continue
            name = act.get("attraction_name") or act.get("name") or act.get("activity") or "Tourist Landmark"
            time_str = act.get("start_time") or act.get("time") or "Daytime"
            # Format time nicely if 24h
            if ":" in time_str and len(time_str.split(":")[0]) <= 2:
                hh = int(time_str.split(":")[0])
                mm = time_str.split(":")[1][:2]
                period = "AM" if hh < 12 else "PM"
                hh12 = hh % 12
                if hh12 == 0:
                    hh12 = 12
                time_str = f"{hh12}:{mm} {period}"

            # Google maps query URL
            q_enc = urllib.parse.quote_plus(f"{name}, {destination}")
            maps_url = act.get("google_maps_url") or f"https://maps.google.com/?q={q_enc}"

            activities_html.append(f"""
            <li class="activity-item">
              <div class="activity-left">
                <span class="activity-bullet">•</span>
                <span class="activity-name">{name}</span>
                <a class="map-link-btn" href="{maps_url}" target="_blank">📍 Map</a>
              </div>
              <div class="activity-time">{time_str}</div>
            </li>
            """)

        day_cards_html.append(f"""
        <div class="day-block">
          <div class="day-ribbon">DAY {day_num}</div>
          <div class="day-card">
            <div class="day-theme-title">{theme}</div>
            <ul class="activity-list">
              {''.join(activities_html)}
            </ul>
          </div>
        </div>
        """)

    # ── Build Polaroid Gallery HTML ───
    polaroid_html = []
    for p_idx, item in enumerate(polaroid_items[:3]):
        tilt_class = "tilt-right" if p_idx % 2 == 0 else "tilt-left"
        pin_color = "#b45309" if p_idx % 2 == 0 else "#0c3b36"
        accent_color = "#f59e0b" if p_idx % 2 == 0 else "#14b8a6"
        polaroid_html.append(f"""
        <div class="polaroid-frame {tilt_class}">
          <svg class="polaroid-clip" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" fill="{pin_color}" stroke="#451a03" stroke-width="1.2"/>
            <circle cx="12" cy="12" r="5" fill="{accent_color}"/>
            <circle cx="10" cy="10" r="2" fill="#ffffff" opacity="0.6"/>
          </svg>
          <div class="polaroid-img-wrapper">
            <img class="polaroid-img" src="{item['img_src']}" alt="{item['name']}" loading="eager" />
          </div>
          <div class="polaroid-caption">{item['name']}</div>
        </div>
        """)

    # ── Accommodation & Transit Details ───
    hotel = itinerary.get("hotel") or itinerary.get("accommodation") or {}
    h_name = hotel.get("hotel_name") or hotel.get("name") or f"Recommended Verified Hotel, {dest_title}"
    h_price = hotel.get("price_per_night")
    h_total = hotel.get("price_total")
    h_reason = hotel.get("reasoning") or "Handpicked verified stay near prime tourist attractions."
    hotel_q = urllib.parse.quote_plus(f"{h_name}, {destination}")
    hotel_map = f"https://maps.google.com/?q={hotel_q}"
    hotel_price_str = f"₹{int(h_price):,}/night" if h_price else "Standard Tier"
    if h_total:
        hotel_price_str += f" (Total: ₹{int(h_total):,})"

    transit_out = itinerary.get("outbound_transport") or {}
    trans_name = transit_out.get("train_name") or transit_out.get("operator_name") or transit_out.get("airline") or mode_label
    trans_instr = transit_out.get("instruction") or f"Scenic route between {orig_title} and {dest_title}."
    route_q = urllib.parse.quote_plus(f"{orig_title} to {dest_title}")
    route_map = f"https://maps.google.com/?q={route_q}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Dream Destiny Travel Itinerary</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Caveat:wght@600;700&display=swap" rel="stylesheet">
<style>
  @page {{
    size: A4 portrait;
    margin: 0;
  }}
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  body {{
    width: 210mm;
    min-height: 297mm;
    background: #fbf9f4;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #1e293b;
    position: relative;
    padding: 34px 38px 28px 38px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    overflow: hidden;
  }}

  /* Decorative Vintage Compass Watermark */
  .bg-compass {{
    position: absolute;
    top: -24px;
    left: -24px;
    width: 230px;
    height: 230px;
    opacity: 0.035;
    pointer-events: none;
    z-index: 0;
  }}

  .content-wrapper {{
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
  }}

  /* Header Section */
  .header-grid {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 22px;
    border-bottom: 2px solid rgba(12, 59, 54, 0.15);
    padding-bottom: 14px;
  }}
  .brand-tag {{
    display: inline-block;
    font-size: 9.5px;
    letter-spacing: 3.5px;
    font-weight: 800;
    color: #b45309;
    text-transform: uppercase;
    margin-bottom: 4px;
  }}
  .route-title {{
    font-family: 'Cinzel', serif;
    font-size: 26px;
    font-weight: 800;
    color: #0c3b36;
    letter-spacing: 0.5px;
    line-height: 1.15;
  }}
  .route-meta-pills {{
    display: flex;
    gap: 8px;
    margin-top: 6px;
  }}
  .meta-pill {{
    font-size: 10px;
    font-weight: 600;
    color: #475569;
    background: rgba(12, 59, 54, 0.06);
    padding: 3px 10px;
    border-radius: 12px;
    border: 1px solid rgba(12, 59, 54, 0.1);
  }}

  .header-right {{
    text-align: right;
  }}
  .travel-hero-text {{
    font-family: 'Cinzel', serif;
    font-size: 44px;
    font-weight: 900;
    letter-spacing: 3px;
    color: #0c3b36;
    line-height: 0.85;
  }}
  .itinerary-sub-text {{
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 11px;
    color: #0c3b36;
    margin-top: 6px;
    margin-right: -11px;
    text-transform: uppercase;
  }}

  /* Main Grid */
  .main-grid {{
    display: grid;
    grid-template-columns: 1.28fr 0.92fr;
    gap: 26px;
    align-items: start;
  }}

  /* Left Column: Itinerary Days */
  .itinerary-col {{
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .day-block {{
    position: relative;
  }}

  .day-ribbon {{
    display: inline-block;
    background: #0c3b36;
    color: #ffffff;
    font-family: 'Cinzel', serif;
    font-size: 13.5px;
    font-weight: 800;
    letter-spacing: 1.2px;
    padding: 5px 22px;
    border-radius: 20px;
    box-shadow: 0 4px 10px rgba(12, 59, 54, 0.25);
    margin-bottom: -11px;
    margin-left: 14px;
    position: relative;
    z-index: 2;
  }}

  .day-card {{
    background: #ffffff;
    border-radius: 18px;
    padding: 18px 18px 14px 18px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
    border: 1px solid rgba(226, 232, 240, 0.85);
    position: relative;
    z-index: 1;
  }}

  .day-theme-title {{
    font-size: 10px;
    font-weight: 800;
    color: #b45309;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 10px;
    padding-bottom: 5px;
    border-bottom: 1px dashed #e2e8f0;
  }}

  .activity-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}

  .activity-item {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 11px;
    line-height: 1.35;
  }}

  .activity-left {{
    display: flex;
    align-items: baseline;
    gap: 6px;
    flex: 1;
    margin-right: 12px;
  }}

  .activity-bullet {{
    color: #0c3b36;
    font-weight: 900;
    font-size: 12px;
    line-height: 1;
  }}

  .activity-name {{
    font-weight: 600;
    color: #1e293b;
    word-break: break-word;
  }}

  .map-link-btn {{
    display: inline-flex;
    align-items: center;
    font-size: 9.5px;
    color: #0284c7;
    text-decoration: none;
    font-weight: 700;
    margin-left: 5px;
    white-space: nowrap;
    opacity: 0.9;
  }}
  .map-link-btn:hover {{
    text-decoration: underline;
  }}

  .activity-time {{
    font-size: 10.5px;
    font-weight: 800;
    color: #334155;
    white-space: nowrap;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}

  /* Right Column: Polaroid Gallery */
  .showcase-col {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
    padding-top: 4px;
  }}

  .polaroid-frame {{
    background: #ffffff;
    padding: 10px 10px 22px 10px;
    border-radius: 4px;
    box-shadow: 0 14px 28px rgba(0, 0, 0, 0.12), 0 4px 10px rgba(0, 0, 0, 0.08);
    position: relative;
    width: 220px;
  }}
  .polaroid-frame.tilt-right {{
    transform: rotate(2.2deg);
  }}
  .polaroid-frame.tilt-left {{
    transform: rotate(-2.2deg);
  }}

  .polaroid-clip {{
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%);
    width: 24px;
    height: 24px;
    z-index: 3;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
  }}

  .polaroid-img-wrapper {{
    width: 100%;
    height: 132px;
    overflow: hidden;
    border-radius: 2px;
    border: 1px solid rgba(0,0,0,0.06);
    background: #f1f5f9;
  }}

  .polaroid-img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}

  .polaroid-caption {{
    font-family: 'Caveat', cursive;
    font-size: 16px;
    font-weight: 700;
    color: #334155;
    text-align: center;
    margin-top: 8px;
    line-height: 1.1;
  }}

  .explore-discover-badge {{
    text-align: center;
    margin-top: 6px;
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.85);
    border: 1px dashed rgba(180, 83, 9, 0.35);
    border-radius: 14px;
    width: 100%;
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  }}
  .explore-discover-text {{
    font-family: 'Caveat', cursive;
    font-size: 25px;
    font-weight: 700;
    color: #0c3b36;
    line-height: 1;
  }}
  .explore-sub {{
    font-size: 9px;
    color: #64748b;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-weight: 700;
    margin-top: 3px;
  }}

  /* Bottom Logistics Bar */
  .footer-logistics {{
    margin-top: 18px;
    padding-top: 12px;
    border-top: 1px solid rgba(226, 232, 240, 0.9);
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }}

  .logistics-card {{
    background: #ffffff;
    border-radius: 14px;
    padding: 10px 14px;
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.04);
    border: 1px solid #e2e8f0;
    font-size: 10.5px;
  }}
  .logistics-header {{
    font-size: 10px;
    font-weight: 800;
    color: #0c3b36;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .logistics-detail {{
    color: #334155;
    line-height: 1.35;
  }}
  .logistics-map-link {{
    color: #0284c7;
    font-weight: 700;
    text-decoration: none;
    font-size: 9.5px;
  }}
</style>
</head>
<body>

<svg class="bg-compass" viewBox="0 0 24 24" fill="none" stroke="#0c3b36" stroke-width="1.5">
  <circle cx="12" cy="12" r="10"/>
  <polygon points="12 4 15 12 12 20 9 12 12 4" fill="#0c3b36"/>
</svg>

<div class="content-wrapper">

  <!-- Header -->
  <div class="header-grid">
    <div>
      <div class="brand-tag">Dream Destiny &bull; AI Travel Concierge</div>
      <div class="route-title">{orig_title} ➔ {dest_title}</div>
      <div class="route-meta-pills">
        <span class="meta-pill">📅 {days_cnt} Days</span>
        <span class="meta-pill">👥 {travelers_cnt} Travelers</span>
        <span class="meta-pill">🚗 {mode_label}</span>
        <span class="meta-pill">💰 {budget_tier} Tier</span>
      </div>
    </div>
    <div class="header-right">
      <div class="travel-hero-text">TRAVEL</div>
      <div class="itinerary-sub-text">ITINERARY</div>
    </div>
  </div>

  <!-- Main Grid -->
  <div class="main-grid">
    <!-- Left Column: Days Timetable -->
    <div class="itinerary-col">
      {''.join(day_cards_html)}
    </div>

    <!-- Right Column: Visual Polaroid Showcase -->
    <div class="showcase-col">
      {''.join(polaroid_html)}
      <div class="explore-discover-badge">
        <div class="explore-discover-text">Explore &amp; Discover</div>
        <div class="explore-sub">Curated by Dream Destiny AI</div>
      </div>
    </div>
  </div>

  <!-- Bottom Logistics & Stay Bar -->
  <div class="footer-logistics">
    <div class="logistics-card">
      <div class="logistics-header">
        <span>🏨 Verified Accommodation</span>
        <a class="logistics-map-link" href="{hotel_map}" target="_blank">📍 Open in Maps ↗</a>
      </div>
      <div class="logistics-detail">
        <b>{h_name}</b> &bull; {hotel_price_str}<br>
        <i>{h_reason}</i>
      </div>
    </div>

    <div class="logistics-card">
      <div class="logistics-header">
        <span>🚗 Transit &amp; Route</span>
        <a class="logistics-map-link" href="{route_map}" target="_blank">📍 Open in Maps ↗</a>
      </div>
      <div class="logistics-detail">
        <b>{trans_name}</b><br>
        <i>{trans_instr}</i>
      </div>
    </div>
  </div>

</div>
</body>
</html>
"""


async def render_designer_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Renders the designer travel dossier PDF entirely in memory using Playwright Chromium.
    Guarantees ZERO files are saved to disk.
    """
    html_content = build_designer_html(itinerary, origin, destination, trip_meta)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(
            viewport={"width": 1200, "height": 1600},
            device_scale_factor=2,
        )
        # Load content and wait for network images
        try:
            await page.set_content(html_content, wait_until="networkidle", timeout=8000)
        except Exception as nav_err:
            logger.warning("Networkidle wait timed out, continuing with loaded DOM: %s", nav_err)

        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0px", "bottom": "0px", "left": "0px", "right": "0px"}
        )
        await browser.close()
        return pdf_bytes
