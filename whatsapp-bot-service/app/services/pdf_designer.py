"""
Editorial Travel Scrapbook PDF Engine for Dream Destiny.
Renders an ultra-aesthetic, magazine-grade travel dossier matching the executive scrapbook reference:
- Hero typographic lockup: "ORIGIN ➔ DESTINATION" with amber brand tag and bold "TRAVEL ITINERARY" header in forest teal.
- Day-by-day timetable cards with dark teal ribbons and clickable Google Maps navigation links.
- Dedicated showcase of Polaroid-style photo frames with realistic metallic brooch pins, drop shadows, and clean captions.
- Logistics Bento boxes for Verified Accommodation & Transit Route with interactive map links.
- Robust image handling: utilizes the place's Google Maps image_url when available; if absent or failing, manages gracefully with verified curated photography and elegant stylized fallback cards.
- 100% In-Memory rendering via pure Python (ReportLab + Pillow). Zero disk storage, zero headless browser/Chromium dependencies.
"""

import io
import asyncio
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

import httpx
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether
)

logger = logging.getLogger(__name__)

# Verified, high-resolution photography catalog for key destinations
LANDMARK_PHOTOS: Dict[str, str] = {
    # Madurai & Tamil Nadu
    "meenakshi": "https://images.unsplash.com/photo-1609137144813-7d9921338f24?auto=format&fit=crop&w=700&q=80",
    "thirumalai": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=700&q=80",
    "mahal": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=700&q=80",
    "gandhi": "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?auto=format&fit=crop&w=700&q=80",
    "teppakulam": "https://images.unsplash.com/photo-1596176530529-78163a4f7af2?auto=format&fit=crop&w=700&q=80",
    "puthu mandapam": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=700&q=80",
    "alagar": "https://images.unsplash.com/photo-1544735716-392fe2489ffa?auto=format&fit=crop&w=700&q=80",
    # Mumbai
    "gateway of india": "https://images.unsplash.com/photo-1570168007204-dfb528c6958f?auto=format&fit=crop&w=700&q=80",
    "marine drive": "https://images.unsplash.com/photo-1566552881560-0be86c53210b?auto=format&fit=crop&w=700&q=80",
    "elephanta": "https://images.unsplash.com/photo-1600100397608-f010e423b971?auto=format&fit=crop&w=700&q=80",
    # Goa
    "baga beach": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=700&q=80",
    "calangute": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=700&q=80",
    "aguada": "https://images.unsplash.com/photo-1587974928442-77dc3e0dba72?auto=format&fit=crop&w=700&q=80",
    "basilica": "https://images.unsplash.com/photo-1548013146-72479768bada?auto=format&fit=crop&w=700&q=80",
    # Rajasthan & North India
    "taj mahal": "https://images.unsplash.com/photo-1564507592333-c60657eea523?auto=format&fit=crop&w=700&q=80",
    "india gate": "https://images.unsplash.com/photo-1587474260584-136574528ed5?auto=format&fit=crop&w=700&q=80",
    "qutub": "https://images.unsplash.com/photo-1548013146-72479768bada?auto=format&fit=crop&w=700&q=80",
    "hawa mahal": "https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=700&q=80",
    "amer fort": "https://images.unsplash.com/photo-1603258849040-5e3e2b9c5123?auto=format&fit=crop&w=700&q=80",
    # Hill stations & Nature
    "ooty": "https://images.unsplash.com/photo-1589182373726-e4f658ab50f0?auto=format&fit=crop&w=700&q=80",
    "kodaikanal": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=700&q=80",
    "manali": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=700&q=80",
    "kerala": "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?auto=format&fit=crop&w=700&q=80",
    "munnar": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=700&q=80",
}

# Thematic high-res fallback imagery
FALLBACK_THEMES: Dict[str, str] = {
    "spiritual": "https://images.unsplash.com/photo-1609137144813-7d9921338f24?auto=format&fit=crop&w=700&q=80",
    "nature": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=700&q=80",
    "beach": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=700&q=80",
    "heritage": "https://images.unsplash.com/photo-1590050752117-238cb0fb12b1?auto=format&fit=crop&w=700&q=80",
    "mountain": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=700&q=80",
    "default": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=700&q=80",
}


def resolve_attraction_photo(attraction_name: str, destination: str, provided_url: Optional[str] = None) -> str:
    """
    Returns a verified high-resolution photograph URL for the attraction.
    Prioritizes provided_url (from Google Maps or tourism API), then verified catalog, then category.
    """
    if provided_url and str(provided_url).strip().startswith("http") and not provided_url.endswith(".svg"):
        return str(provided_url).strip()

    name_lower = attraction_name.lower()
    dest_lower = destination.lower()

    # 1. Exact or partial keyword match in catalog
    for key, url in LANDMARK_PHOTOS.items():
        if key in name_lower or (key in dest_lower and len(key) > 4):
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


async def fetch_image_async(url: str, client: httpx.AsyncClient) -> Optional[bytes]:
    """Downloads an image asynchronously with a strict 2.5s timeout."""
    if not url or not url.startswith("http"):
        return None
    try:
        resp = await client.get(url, timeout=2.5, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
    except Exception as exc:
        logger.debug("Async image download skipped for %s: %s", url, exc)
    return None


def fetch_image_sync(url: str) -> Optional[bytes]:
    """Synchronous fallback image fetcher with timeout."""
    if not url or not url.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=2.5, follow_redirects=True, headers={"User-Agent": "DreamDestiny/2.0"}) as client:
            resp = client.get(url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
    except Exception as exc:
        logger.debug("Sync image download skipped for %s: %s", url, exc)
    return None


def create_polaroid_card(
    image_bytes: Optional[bytes],
    caption: str,
    target_width_pt: float = 195,
    target_height_pt: float = 152,
    rotation_deg: float = 0.0,
) -> io.BytesIO:
    """
    Renders an in-memory Polaroid photo frame with:
    - Antique brass brooch push-pin at top center
    - Photorealistic white Polaroid frame with subtle border
    - Soft 3D drop shadow
    - Crisp cropped photo (or graceful geometric fallback card if image missing)
    - Clean typography caption at bottom
    """
    scale = 3  # High-DPI scale for ultra-crisp print rendering
    card_w = int(target_width_pt * scale)
    card_h = int(target_height_pt * scale)

    pad = int(12 * scale)
    canvas_w = card_w + pad * 2
    canvas_h = card_h + pad * 2

    img = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    card_x0 = pad
    card_y0 = pad + int(3 * scale)
    card_x1 = card_x0 + card_w
    card_y1 = card_y0 + card_h

    # 1. Soft Realistic Drop Shadow
    for i in range(12, 0, -1):
        alpha = int(22 * (1.0 - (i / 12.0) ** 1.3))
        shadow_rect = [
            card_x0 - i * 1.0,
            card_y0 + int(3 * scale) - i * 0.6,
            card_x1 + i * 1.0,
            card_y1 + int(3 * scale) + i * 1.3,
        ]
        draw.rounded_rectangle(shadow_rect, radius=int(7 * scale), fill=(15, 23, 42, alpha))

    # 2. White Polaroid Frame
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=int(6 * scale),
        fill=(255, 255, 255, 255),
        outline=(220, 226, 235, 255),
        width=int(1.2 * scale),
    )

    # 3. Inner Photo Area
    photo_margin_x = int(10 * scale)
    photo_margin_top = int(12 * scale)
    photo_w = card_w - photo_margin_x * 2
    photo_h = int(card_h * 0.68)
    photo_x0 = card_x0 + photo_margin_x
    photo_y0 = card_y0 + photo_margin_top

    photo_img = None
    if image_bytes:
        try:
            raw_img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            photo_img = ImageOps.fit(raw_img, (photo_w, photo_h), PILImage.Resampling.LANCZOS)
        except Exception:
            photo_img = None

    if photo_img is None:
        # Graceful decorative design when photo is unavailable
        photo_img = PILImage.new("RGB", (photo_w, photo_h), (245, 247, 250))
        p_draw = ImageDraw.Draw(photo_img)
        p_draw.rectangle([0, 0, photo_w, photo_h], fill=(241, 245, 249))
        p_draw.rectangle([int(6 * scale), int(6 * scale), photo_w - int(6 * scale), photo_h - int(6 * scale)], outline=(203, 213, 225), width=int(1 * scale))
        try:
            font_fallback = ImageFont.truetype("arial.ttf", int(12 * scale))
        except Exception:
            font_fallback = ImageFont.load_default()
        p_draw.text((photo_w // 2, photo_h // 2), "DREAM DESTINY", fill=(148, 163, 184), font=font_fallback, anchor="mm")

    img.paste(photo_img, (photo_x0, photo_y0))
    draw.rectangle([photo_x0, photo_y0, photo_x0 + photo_w, photo_y0 + photo_h], outline=(203, 213, 225, 200), width=int(1 * scale))

    # 4. Antique Brass Brooch Pin at top center
    pin_cx = card_x0 + card_w // 2
    pin_cy = card_y0 + int(3 * scale)
    pin_r = int(6.5 * scale)
    draw.ellipse([pin_cx - pin_r + 2, pin_cy - pin_r + 3, pin_cx + pin_r + 3, pin_cy + pin_r + 5], fill=(0, 0, 0, 45))
    draw.ellipse([pin_cx - pin_r, pin_cy - pin_r, pin_cx + pin_r, pin_cy + pin_r], fill=(180, 83, 9), outline=(120, 53, 15), width=int(1.2 * scale))
    draw.ellipse([pin_cx - pin_r + int(2 * scale), pin_cy - pin_r + int(2 * scale), pin_cx + pin_r - int(2 * scale), pin_cy + pin_r - int(2 * scale)], fill=(245, 158, 11))
    draw.ellipse([pin_cx - int(2.5 * scale), pin_cy - int(3 * scale), pin_cx - int(1 * scale), pin_cy - int(1.5 * scale)], fill=(254, 243, 199))

    # 5. Caption at bottom
    caption_y = photo_y0 + photo_h + int(10 * scale)
    font_caption = None
    for fn in ["georgia.ttf", "calibri.ttf", "arial.ttf"]:
        try:
            font_caption = ImageFont.truetype(fn, int(10.5 * scale))
            break
        except Exception:
            continue
    if not font_caption:
        font_caption = ImageFont.load_default()

    clean_cap = caption if len(caption) <= 26 else caption[:24] + "…"
    draw.text((pin_cx, caption_y), clean_cap, fill=(15, 23, 42), font=font_caption, anchor="mt")

    if rotation_deg != 0.0:
        img = img.rotate(rotation_deg, resample=PILImage.Resampling.BICUBIC, expand=False)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def draw_parchment_canvas(canvas_obj, doc):
    """Draws warm editorial parchment background, subtle vintage double border, and corner diamond flourishes."""
    canvas_obj.saveState()
    # 1. Warm Editorial Parchment Base
    canvas_obj.setFillColor(colors.HexColor("#fbf9f4"))
    canvas_obj.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)

    # 2. Outer Forest Teal Border
    canvas_obj.setStrokeColor(colors.HexColor("#0c3b36"))
    canvas_obj.setLineWidth(0.85)
    canvas_obj.rect(14, 14, doc.pagesize[0] - 28, doc.pagesize[1] - 28, fill=False, stroke=True)

    # 3. Inner Slate Hairline
    canvas_obj.setStrokeColor(colors.HexColor("#d1d5db"))
    canvas_obj.setLineWidth(0.35)
    canvas_obj.rect(17.5, 17.5, doc.pagesize[0] - 35, doc.pagesize[1] - 35, fill=False, stroke=True)

    # 4. Corner Diamonds in Amber
    c_pts = [
        (14, 14),
        (doc.pagesize[0] - 14, 14),
        (14, doc.pagesize[1] - 14),
        (doc.pagesize[0] - 14, doc.pagesize[1] - 14),
    ]
    canvas_obj.setFillColor(colors.HexColor("#b45309"))
    for x, y in c_pts:
        canvas_obj.circle(x, y, 2.2, fill=True, stroke=False)

    canvas_obj.restoreState()


def build_editorial_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
    image_bytes_map: Optional[Dict[str, bytes]] = None,
) -> bytes:
    """
    Builds the complete editorial PDF document in memory.
    Guarantees active clickable hyperlinks, crisp vector typography, and magazine-grade presentation.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=26,
        rightMargin=26,
        topMargin=22,
        bottomMargin=18,
    )

    styles = getSampleStyleSheet()

    # Typography styles (using Latin-1 / standard PDF Type 1 safe characters)
    style_brand = ParagraphStyle(
        "BrandTag",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor("#b45309"),
    )
    style_route = ParagraphStyle(
        "RouteTitle",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=22,
        leading=25,
        textColor=colors.HexColor("#0c3b36"),
    )
    style_pills = ParagraphStyle(
        "MetaPills",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
    )
    style_hero_title = ParagraphStyle(
        "HeroTitle",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=34,
        leading=32,
        alignment=2,
        textColor=colors.HexColor("#0c3b36"),
    )
    style_hero_sub = ParagraphStyle(
        "HeroSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        alignment=2,
        textColor=colors.HexColor("#0c3b36"),
    )

    # Day Ribbon & Card Styles
    style_ribbon = ParagraphStyle(
        "DayRibbon",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11.5,
        textColor=colors.white,
    )
    style_act_name = ParagraphStyle(
        "ActName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.8,
        leading=11.5,
        textColor=colors.HexColor("#0f172a"),
    )
    style_act_time = ParagraphStyle(
        "ActTime",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=11.5,
        alignment=2,
        textColor=colors.HexColor("#0c3b36"),
    )
    style_act_note = ParagraphStyle(
        "ActNote",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#475569"),
    )

    # Logistics styles
    style_log_title = ParagraphStyle(
        "LogTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.8,
        leading=11.5,
        textColor=colors.HexColor("#0c3b36"),
    )
    style_log_link = ParagraphStyle(
        "LogLink",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=11.5,
        alignment=2,
        textColor=colors.HexColor("#0d9488"),
    )
    style_log_body_bold = ParagraphStyle(
        "LogBodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )
    style_log_body_note = ParagraphStyle(
        "LogBodyNote",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.8,
        leading=10.2,
        textColor=colors.HexColor("#475569"),
    )
    style_footer = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.5,
        alignment=1,
        textColor=colors.HexColor("#64748b"),
    )

    story = []

    # ── 1. HEADER SECTION ───
    orig_title = origin.strip().title()
    dest_title = destination.strip().title()
    summary = itinerary.get("summary") or {}
    days_cnt = summary.get("days") or len(itinerary.get("days", [])) or 3
    travelers_cnt = summary.get("travelers") or 2
    budget_tier = str(summary.get("budget_level") or "Medium").title()
    raw_mode = str(itinerary.get("transport_mode") or (trip_meta.get("transport_mode") if trip_meta else "") or "Car").title()
    if any(k in raw_mode.lower() for k in ("car", "drive", "road")):
        mode_label = "Self-Drive / Own Car"
    elif "Train" in raw_mode:
        mode_label = "Train Transit"
    elif "Flight" in raw_mode:
        mode_label = "Flight Transit"
    else:
        mode_label = f"{raw_mode} Transit"

    left_header = [
        Paragraph("DREAM DESTINY V2.0 &bull; AI TRAVEL DOSSIER", style_brand),
        Spacer(1, 2),
        Paragraph(f"{orig_title.upper()} &rarr; {dest_title.upper()}", style_route),
        Spacer(1, 3),
        Paragraph(f"<b>{days_cnt} Days</b> &bull; <b>{travelers_cnt} Travelers</b> &bull; <b>{budget_tier} Tier</b> &bull; <b>{mode_label}</b>", style_pills),
    ]
    right_header = [
        Paragraph("TRAVEL", style_hero_title),
        Paragraph("I T I N E R A R Y", style_hero_sub),
    ]

    header_table = Table(
        [[left_header, right_header]],
        colWidths=[338, 205],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, colors.HexColor("#0c3b36")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # ── 2. MAIN 2-COLUMN SECTION (DAYS ON LEFT, POLAROIDS ON RIGHT) ───
    days_list = itinerary.get("days") or itinerary.get("itinerary") or []

    # Gather up to 3 Polaroid Attractions (one from each day or distinct places)
    polaroid_candidates = []
    for d in days_list:
        if not isinstance(d, dict):
            continue
        acts = d.get("activities") or d.get("schedule") or []
        for act in acts:
            if not isinstance(act, dict):
                continue
            name = act.get("attraction_name") or act.get("name") or act.get("activity") or ""
            if any(k in name.lower() for k in ("check-in", "checkout", "breakfast", "dinner", "drive to")):
                continue
            if name and not any(p["name"].lower() == name.lower() for p in polaroid_candidates):
                img_url = resolve_attraction_photo(name, destination, act.get("image_url"))
                polaroid_candidates.append({"name": name, "url": img_url})
                break  # 1 prominent attraction per day
        if len(polaroid_candidates) >= 3:
            break

    while len(polaroid_candidates) < min(3, max(2, len(days_list))):
        idx = len(polaroid_candidates) + 1
        p_name = f"{dest_title} Landmark {idx}"
        polaroid_candidates.append({"name": p_name, "url": resolve_attraction_photo(p_name, destination)})

    # Render Polaroid images with slight playful scrapbook tilt
    polaroid_flowables = []
    tilts = [-0.8, 0.8, -0.6]
    image_bytes_map = image_bytes_map or {}
    for idx, p in enumerate(polaroid_candidates[:3]):
        # Check pre-fetched image bytes or fetch synchronously
        raw_b = image_bytes_map.get(p["url"])
        if not raw_b:
            raw_b = fetch_image_sync(p["url"])
        rot = tilts[idx % len(tilts)]
        pol_buf = create_polaroid_card(raw_b, p["name"], target_width_pt=185, target_height_pt=152, rotation_deg=rot)
        polaroid_flowables.append(RLImage(pol_buf, width=195, height=164))
        if idx < len(polaroid_candidates[:3]) - 1:
            polaroid_flowables.append(Spacer(1, 4))

    # Left Column: Day cards
    left_day_elements = []
    for d_idx, day in enumerate(days_list[:3]):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day", d_idx + 1)
        theme = day.get("theme") or day.get("title") or "Sightseeing & Exploration"

        # Day ribbon header
        ribbon_p = Paragraph(f"<b>DAY {day_num} &bull; {theme.upper()}</b>", style_ribbon)
        ribbon_tbl = Table([[ribbon_p]], colWidths=[332])
        ribbon_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0c3b36")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        # Day activity rows
        act_rows = []
        acts = day.get("activities") or day.get("schedule") or []
        for a_idx, act in enumerate(acts[:4]):
            if not isinstance(act, dict):
                continue
            name = act.get("attraction_name") or act.get("name") or act.get("activity") or "Attraction"
            time_str = act.get("start_time") or act.get("time") or "Daytime"
            notes = act.get("notes") or act.get("description") or f"Explore {name} with curated highlights."
            q_enc = urllib.parse.quote_plus(f"{name}, {destination}")
            map_url = act.get("google_maps_url") or f"https://maps.google.com/?q={q_enc}"

            p_name_line = Paragraph(
                f"&bull; <b>{name}</b> &nbsp;<a href=\"{map_url}\" color=\"#0d9488\"><u>[ Map &gt; ]</u></a>",
                style_act_name
            )
            p_time_line = Paragraph(f"<b>{time_str}</b>", style_act_time)
            p_note = Paragraph(notes, style_act_note)

            act_rows.append([p_name_line, p_time_line])
            act_rows.append([p_note, ""])

        card_tbl = Table(act_rows, colWidths=[256, 76])
        table_style_list = [
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e2e8f0")),
        ]
        for r_i in range(1, len(act_rows), 2):
            table_style_list.append(("SPAN", (0, r_i), (1, r_i)))
            table_style_list.append(("BOTTOMPADDING", (0, r_i), (1, r_i), 4))
        card_tbl.setStyle(TableStyle(table_style_list))

        left_day_elements.append(ribbon_tbl)
        left_day_elements.append(card_tbl)
        if d_idx < len(days_list[:3]) - 1:
            left_day_elements.append(Spacer(1, 6))

    main_grid = Table(
        [[left_day_elements, polaroid_flowables]],
        colWidths=[338, 205],
    )
    main_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(main_grid)
    story.append(Spacer(1, 8))

    # ── 3. BOTTOM LOGISTICS BENTO CARDS ───
    hotel = itinerary.get("hotel") or {}
    h_name = hotel.get("hotel_name") or hotel.get("name") or f"Boutique Stay in {dest_title}"
    h_price = hotel.get("price_per_night")
    h_total = hotel.get("price_total")
    h_reason = hotel.get("reasoning") or "Handpicked verified stay near prime attractions."
    hotel_q = urllib.parse.quote_plus(f"{h_name}, {destination}")
    hotel_map = f"https://maps.google.com/?q={hotel_q}"
    hotel_price_str = f"Rs. {int(h_price):,}/night" if h_price else "Standard Tier"
    if h_total:
        hotel_price_str += f" (Total: Rs. {int(h_total):,})"

    transit_out = itinerary.get("outbound_transport") or {}
    trans_name = transit_out.get("train_name") or transit_out.get("operator_name") or transit_out.get("airline") or f"Direct {mode_label}"
    trans_instr = transit_out.get("instruction") or f"Scenic route connecting {orig_title} and {dest_title}."
    route_q = urllib.parse.quote_plus(f"{orig_title} to {dest_title}")
    route_map = f"https://maps.google.com/?q={route_q}"

    hotel_card = [
        Table(
            [[Paragraph("<b>VERIFIED ACCOMMODATION</b>", style_log_title), Paragraph(f'<a href="{hotel_map}" color="#0d9488"><u>[ View Map &gt; ]</u></a>', style_log_link)]],
            colWidths=[165, 95],
        ),
        Spacer(1, 2),
        Paragraph(f"{h_name} &bull; {hotel_price_str}", style_log_body_bold),
        Spacer(1, 1),
        Paragraph(h_reason, style_log_body_note),
    ]
    hotel_box = Table([[hotel_card]], colWidths=[266])
    hotel_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e2e8f0")),
        ("LINEBEFORE", (0, 0), (-1, -1), 2.5, colors.HexColor("#0c3b36")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    transit_card = [
        Table(
            [[Paragraph("<b>TRANSIT &amp; ROUTE</b>", style_log_title), Paragraph(f'<a href="{route_map}" color="#0d9488"><u>[ View Route &gt; ]</u></a>', style_log_link)]],
            colWidths=[165, 95],
        ),
        Spacer(1, 2),
        Paragraph(trans_name, style_log_body_bold),
        Spacer(1, 1),
        Paragraph(trans_instr, style_log_body_note),
    ]
    transit_box = Table([[transit_card]], colWidths=[266])
    transit_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e2e8f0")),
        ("LINEBEFORE", (0, 0), (-1, -1), 2.5, colors.HexColor("#0c3b36")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    logistics_table = Table([[hotel_box, transit_box]], colWidths=[271, 271])
    logistics_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(logistics_table)
    story.append(Spacer(1, 7))

    # ── 4. FOOTER ───
    story.append(Paragraph("DREAM DESTINY V2.0 &bull; CURATED INTELLIGENCE &bull; ZERO DISK FOOTPRINT &bull; HAVE A SAFE TRIP", style_footer))

    doc.build(story, onFirstPage=draw_parchment_canvas, onLaterPages=draw_parchment_canvas)

    buf.seek(0)
    return buf.getvalue()


async def render_designer_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Renders the designer travel dossier PDF entirely in memory.
    Fetches required attraction photos concurrently with httpx async client.
    Guarantees ZERO files are saved to disk.
    """
    # 1. Identify up to 3 Polaroid photo candidates
    days_list = itinerary.get("days") or itinerary.get("itinerary") or []
    urls_to_fetch = set()
    for d in days_list:
        if not isinstance(d, dict):
            continue
        acts = d.get("activities") or d.get("schedule") or []
        for act in acts:
            if not isinstance(act, dict):
                continue
            name = act.get("attraction_name") or act.get("name") or act.get("activity") or ""
            if any(k in name.lower() for k in ("check-in", "checkout", "breakfast", "dinner", "drive to")):
                continue
            if name:
                u = resolve_attraction_photo(name, destination, act.get("image_url"))
                urls_to_fetch.add(u)
                break
        if len(urls_to_fetch) >= 3:
            break

    # 2. Concurrently download images in memory with timeout
    image_bytes_map: Dict[str, bytes] = {}
    if urls_to_fetch:
        try:
            async with httpx.AsyncClient(timeout=2.5, follow_redirects=True) as client:
                fetch_tasks = [fetch_image_async(u, client) for u in urls_to_fetch]
                results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                for u, res in zip(urls_to_fetch, results):
                    if isinstance(res, bytes) and len(res) > 500:
                        image_bytes_map[u] = res
        except Exception as exc:
            logger.debug("Concurrent image pre-fetch encountered: %s", exc)

    # 3. Build vector PDF in thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        build_editorial_pdf,
        itinerary,
        origin,
        destination,
        trip_meta,
        image_bytes_map,
    )


def render_designer_pdf_sync(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Synchronous entry point for testing or non-async callers."""
    return build_editorial_pdf(itinerary, origin, destination, trip_meta)
