"""
Executive PDF Travel Dossier Generator.
Creates a luxury, magazine-quality, printable PDF itinerary directly in memory.
Guarantees ZERO files are saved to disk.
Includes side-by-side tourist attraction photography and clickable Google Maps navigation links.
"""

import io
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional

import httpx
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage, ImageDraw

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """Canvas that computes total pages dynamically and adds executive headers & footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running header on pages > 1
        if self._pageNumber > 1:
            self.drawString(36, 812, "DREAM DESTINY ✦ LUXURY AI TRAVEL DOSSIER")
            self.drawRightString(559, 812, f"Page {self._pageNumber} of {page_count}")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(36, 806, 559, 806)

        # Running footer on all pages
        self.setFont("Helvetica", 8)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 30, 559, 30)
        self.drawString(36, 20, "CONFIDENTIAL & PREPARED EXCLUSIVELY FOR TRAVELER • DREAM DESTINY AI CONCIERGE")
        self.drawRightString(559, 20, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def create_placeholder_thumbnail(attraction_name: str, category: str = "") -> io.BytesIO:
    """Generates a modern, elegant visual card for attractions without external images."""
    w, h = 360, 240
    low_name = attraction_name.lower()
    if any(k in low_name for k in ("temple", "church", "mosque", "meenakshi", "shrine", "spiritual")):
        bg_col = (180, 83, 9)     # Warm Gold/Amber
        tag = "SPIRITUAL HERITAGE"
    elif any(k in low_name for k in ("beach", "lake", "falls", "river", "sea", "ocean", "water")):
        bg_col = (13, 148, 136)   # Deep Teal
        tag = "COASTAL & NATURE"
    elif any(k in low_name for k in ("fort", "palace", "museum", "monument", "gateway", "mahal")):
        bg_col = (15, 23, 42)     # Midnight Slate
        tag = "HISTORIC MONUMENT"
    elif any(k in low_name for k in ("garden", "park", "wildlife", "hill", "valley", "trek")):
        bg_col = (21, 128, 61)    # Forest Emerald
        tag = "SCENIC & OUTDOORS"
    elif any(k in low_name for k in ("shop", "bazaar", "market", "food", "idli", "restaurant", "cafe")):
        bg_col = (194, 65, 12)    # Sunset Crimson
        tag = "CUISINE & CULTURE"
    else:
        bg_col = (30, 41, 59)     # Charcoal Slate
        tag = "POINTS OF INTEREST"

    img = PILImage.new("RGB", (w, h), color=bg_col)
    draw = ImageDraw.Draw(img)

    # Accent decorative borders
    draw.rectangle([6, 6, w - 6, h - 6], outline=(255, 255, 255), width=2)
    draw.rectangle([12, 12, w - 12, 40], fill=(255, 255, 255))
    draw.text((20, 20), f"DREAM DESTINY  |  {tag}", fill=bg_col)

    display_title = attraction_name[:26] + "..." if len(attraction_name) > 26 else attraction_name
    draw.text((22, 95), display_title, fill=(255, 255, 255))
    draw.text((22, 140), "GPS VERIFIED LOCATION", fill=(203, 213, 225))
    draw.text((22, 175), "CLICK TO NAVIGATE (MAPS)", fill=(56, 189, 248))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def fetch_or_create_thumbnail(attraction_name: str, image_url: Optional[str] = None) -> io.BytesIO:
    """Attempts to fetch external image or falls back to custom generated visual card."""
    if image_url and str(image_url).startswith("http"):
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(image_url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    pil_img = PILImage.open(io.BytesIO(resp.content)).convert("RGB")
                    pil_img = pil_img.resize((360, 240))
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=85)
                    buf.seek(0)
                    return buf
        except Exception:
            pass

    return create_placeholder_thumbnail(attraction_name)


def generate_itinerary_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Builds a luxury, executive, magazine-quality PDF Travel Dossier entirely in memory.
    Guarantees ZERO files are saved to disk.
    Includes side-by-side attraction photography and clickable Google Maps navigation hyperlinks.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom Luxury Styles
    primary_color = colors.HexColor("#0F172A")
    teal_color = colors.HexColor("#0D9488")
    gold_color = colors.HexColor("#D97706")
    slate_dark = colors.HexColor("#1E293B")
    muted_color = colors.HexColor("#64748B")
    border_color = colors.HexColor("#E2E8F0")
    surface_color = colors.HexColor("#F8FAFC")
    link_color = colors.HexColor("#0284C7")

    style_hero_tag = ParagraphStyle(
        "HeroTag",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#F59E0B"),
    )
    style_hero_title = ParagraphStyle(
        "HeroTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.white,
    )
    style_hero_sub = ParagraphStyle(
        "HeroSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#E2E8F0"),
    )
    style_stat_label = ParagraphStyle(
        "StatLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=primary_color,
    )
    style_stat_val = ParagraphStyle(
        "StatVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=muted_color,
    )
    style_sec_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=primary_color,
    )
    style_card_title = ParagraphStyle(
        "CardTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=primary_color,
    )
    style_card_meta = ParagraphStyle(
        "CardMeta",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10.5,
        textColor=teal_color,
    )
    style_card_body = ParagraphStyle(
        "CardBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=slate_dark,
    )
    style_link = ParagraphStyle(
        "CardLink",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=link_color,
    )

    story = []

    orig_title = origin.strip().title()
    dest_title = destination.strip().title()

    # 1. Executive Hero Header Banner
    header_content = [
        Paragraph("DREAM DESTINY ✦ AI TRAVEL CONCIERGE", style_hero_tag),
        Spacer(1, 3),
        Paragraph(f"{orig_title.upper()} ➔ {dest_title.upper()} EXPEDITION", style_hero_title),
        Spacer(1, 3),
        Paragraph("EXECUTIVE TRAVEL DOSSIER & ITINERARY BROCHURE", style_hero_sub),
    ]
    hero_table = Table([[header_content]], colWidths=[523])
    hero_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("BOX", (0, 0), (-1, -1), 1, primary_color),
    ]))
    story.append(hero_table)
    story.append(Spacer(1, 8))

    # 2. Key Trip Specifications Bar
    summary = itinerary.get("summary") or {}
    days_cnt = summary.get("days") or len(itinerary.get("days", [])) or 3
    travelers_cnt = summary.get("travelers") or 2
    budget_tier = str(summary.get("budget_level") or "Medium").title()
    pace_tier = str(summary.get("pace") or "Moderate").title()
    raw_mode = str(itinerary.get("transport_mode") or (trip_meta.get("transport_mode") if trip_meta else "") or "Any").title()

    stats_cells = [
        [
            Paragraph("📅 DURATION", style_stat_label),
            Paragraph("👥 TRAVELERS", style_stat_label),
            Paragraph("💰 BUDGET TIER", style_stat_label),
            Paragraph("⚡ PACE", style_stat_label),
            Paragraph("🚗 TRANSIT", style_stat_label),
        ],
        [
            Paragraph(f"<b>{days_cnt} Days</b>", style_stat_val),
            Paragraph(f"<b>{travelers_cnt} Persons</b>", style_stat_val),
            Paragraph(f"<b>{budget_tier}</b>", style_stat_val),
            Paragraph(f"<b>{pace_tier}</b>", style_stat_val),
            Paragraph(f"<b>{raw_mode}</b>", style_stat_val),
        ]
    ]
    stats_table = Table(stats_cells, colWidths=[104, 104, 105, 105, 105])
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), surface_color),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 10))

    # 3. Transit & Commute Card
    transit_rows = []
    outbound = itinerary.get("outbound_transport")
    ret_trans = itinerary.get("return_transport")

    if outbound and isinstance(outbound, dict):
        mode = outbound.get("mode", "Transit").title()
        t_name = outbound.get("train_name") or outbound.get("operator_name") or outbound.get("airline") or "Direct Route"
        dep_s = outbound.get("departure_station") or orig_title
        arr_s = outbound.get("arrival_station") or dest_title
        dep_t = outbound.get("departure_time") or ""
        arr_t = outbound.get("arrival_time") or ""
        fare = outbound.get("fare_per_person")
        instr = outbound.get("instruction") or ""

        details_txt = f"<b>{t_name}</b> ({mode})<br/>"
        details_txt += f"Route: <i>{dep_s} ➔ {arr_s}</i>"
        if dep_t or arr_t:
            details_txt += f"  •  ⏰ {dep_t} ➔ {arr_t}"
        if fare:
            details_txt += f"  •  ₹{fare:,}/person"
        if instr:
            details_txt += f"<br/>💡 <i>{instr}</i>"

        transit_rows.append([Paragraph("<b>OUTBOUND JOURNEY:</b>", style_card_meta), Paragraph(details_txt, style_card_body)])

    if ret_trans and isinstance(ret_trans, dict):
        mode = ret_trans.get("mode", "Transit").title()
        t_name = ret_trans.get("train_name") or ret_trans.get("operator_name") or ret_trans.get("airline") or "Direct Route"
        dep_s = ret_trans.get("departure_station") or dest_title
        arr_s = ret_trans.get("arrival_station") or orig_title
        dep_t = ret_trans.get("departure_time") or ""
        arr_t = ret_trans.get("arrival_time") or ""
        fare = ret_trans.get("fare_per_person")

        details_txt = f"<b>{t_name}</b> ({mode})<br/>"
        details_txt += f"Route: <i>{dep_s} ➔ {arr_s}</i>"
        if dep_t or arr_t:
            details_txt += f"  •  ⏰ {dep_t} ➔ {arr_t}"
        if fare:
            details_txt += f"  •  ₹{fare:,}/person"

        transit_rows.append([Paragraph("<b>RETURN JOURNEY:</b>", style_card_meta), Paragraph(details_txt, style_card_body)])

    if not transit_rows and any(k in raw_mode.lower() for k in ("car", "drive", "road")):
        road_txt = (
            f"<b>Self-Drive / Own Car Highway Route</b><br/>"
            f"Scenic National Highway route connecting {orig_title} and {dest_title}.<br/>"
            "💡 Fuel, toll charges, and local attraction parking allocations calculated in overall trip budget."
        )
        transit_rows.append([Paragraph("<b>ROAD EXPEDITION:</b>", style_card_meta), Paragraph(road_txt, style_card_body)])

    if transit_rows:
        story.append(Paragraph("🚗  TRANSIT & COMMUTE OVERVIEW", style_sec_heading))
        story.append(Spacer(1, 3))
        trans_table = Table(transit_rows, colWidths=[120, 403])
        trans_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), surface_color),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(trans_table)
        story.append(Spacer(1, 10))

    # 4. Accommodation & Stay Card with Clickable Google Maps Hyperlink
    hotel = itinerary.get("hotel") or itinerary.get("accommodation")
    if hotel and isinstance(hotel, dict):
        h_name = hotel.get("hotel_name") or hotel.get("name") or "Recommended Luxury Stay"
        h_price = hotel.get("price_per_night")
        h_total = hotel.get("price_total")
        h_reason = hotel.get("reasoning") or "Handpicked verified accommodation located near prime attractions."

        q = urllib.parse.quote_plus(f"{h_name}, {destination}")
        hotel_map_link = f"https://maps.google.com/?q={q}"

        hotel_content = (
            f"<b>{h_name}</b><br/>"
        )
        if h_price:
            price_txt = f"₹{int(h_price):,}/night"
            if h_total:
                price_txt += f"  (Estimated Stay Total: ₹{int(h_total):,})"
            hotel_content += f"💰 Rate: {price_txt}<br/>"
        hotel_content += f"💡 <i>{h_reason}</i><br/>"
        hotel_content += f'<font color="#0284C7"><u><a href="{hotel_map_link}"><b>📍 Open Hotel in Google Maps ↗</b></a></u></font>'

        story.append(Paragraph("🏨  ACCOMMODATION & STAY", style_sec_heading))
        story.append(Spacer(1, 3))
        hotel_table = Table([[
            Paragraph("<b>VERIFIED STAY:</b>", style_card_meta),
            Paragraph(hotel_content, style_card_body)
        ]], colWidths=[120, 403])
        hotel_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), surface_color),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(hotel_table)
        story.append(Spacer(1, 12))

    # 5. Day-by-Day Itinerary with Side-by-Side Images & Google Maps Links
    days_list = itinerary.get("days") or itinerary.get("itinerary") or []
    if days_list and isinstance(days_list, list):
        story.append(Paragraph("📅  DETAILED DAY-BY-DAY ITINERARY", style_sec_heading))
        story.append(Spacer(1, 5))

        for day in days_list:
            if not isinstance(day, dict):
                continue
            day_num = day.get("day", 1)
            date_str = day.get("date", "")
            theme = day.get("theme") or day.get("title") or "Sightseeing & Immersion"

            day_header_txt = f"DAY {day_num}: {theme.upper()}"
            if date_str:
                day_header_txt += f"  •  {date_str}"

            day_banner = Table([[Paragraph(f"<b>{day_header_txt}</b>", ParagraphStyle(
                "DayBanner", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=primary_color
            ))]], colWidths=[523])
            day_banner.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(day_banner)
            story.append(Spacer(1, 5))

            activities = day.get("activities") or day.get("schedule") or []
            for act in activities:
                if not isinstance(act, dict):
                    continue
                name = act.get("attraction_name") or act.get("name") or act.get("activity") or "Attraction Spot"
                start_t = act.get("start_time") or act.get("time") or ""
                dur = act.get("duration_minutes") or ""
                notes = act.get("notes") or act.get("description") or "Curated tourist landmark with unique heritage."
                image_url = act.get("image_url")

                # Clickable Google Maps Link
                q_act = urllib.parse.quote_plus(f"{name}, {destination}")
                maps_url = act.get("google_maps_url") or f"https://maps.google.com/?q={q_act}"

                # Generate thumbnail in memory
                thumb_buf = fetch_or_create_thumbnail(name, image_url)
                thumb_img = Image(thumb_buf, width=115, height=76)

                meta_line = ""
                if start_t:
                    meta_line += f"⏰ {start_t}"
                if dur:
                    meta_line += f"  •  ⌛ {dur} mins"
                meta_line += "  •  ✅ Verified Location"

                act_cell_content = [
                    Paragraph(f"<b>{name}</b>", style_card_title),
                    Spacer(1, 2),
                    Paragraph(meta_line, style_card_meta),
                    Spacer(1, 2),
                    Paragraph(notes, style_card_body),
                    Spacer(1, 2),
                    Paragraph(f'<font color="#0284C7"><u><a href="{maps_url}"><b>📍 Open in Google Maps ↗</b></a></u></font>', style_link),
                ]

                act_row = Table([[thumb_img, act_cell_content]], colWidths=[120, 403])
                act_row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), surface_color),
                    ("BOX", (0, 0), (-1, -1), 0.75, border_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(KeepTogether([act_row]))
                story.append(Spacer(1, 5))

            story.append(Spacer(1, 4))

    # 6. Essential Packing & Travel Advisory Checklist
    story.append(Spacer(1, 4))
    story.append(Paragraph("🧳  ESSENTIAL PACKING & TRAVEL CHECKLIST", style_sec_heading))
    story.append(Spacer(1, 3))

    packing_left = (
        "<b>Documents & Essentials:</b><br/>"
        "• Original Government Photo ID (Aadhaar / Passport)<br/>"
        "• Confirmed transit tickets & hotel booking confirmation<br/>"
        "• Cash in small denominations for local vendors & temple entry<br/>"
        "• Portable power bank (10,000+ mAh) and charging cables"
    )
    packing_right = (
        "<b>Apparel & Health:</b><br/>"
        "• Modest temple-appropriate clothing (covered shoulders & legs)<br/>"
        "• Comfortable walking footwear / slip-on shoes for temple visits<br/>"
        "• Personal medicines, hand sanitizer & electrolyte sachets<br/>"
        "• Sunglasses, sunscreen lotion & reusable water bottle"
    )

    pack_table = Table([[
        Paragraph(packing_left, style_card_body),
        Paragraph(packing_right, style_card_body)
    ]], colWidths=[258, 265])
    pack_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), surface_color),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(pack_table)
    story.append(Spacer(1, 8))

    # 7. 24/7 Emergency Assistance Card
    emerg_txt = (
        "<b>24/7 Helpline Directory:</b>  "
        "National Emergency: <b>112</b>  •  Ambulance: <b>108</b>  •  Police: <b>100</b>  •  "
        "Tourist Helpline: <b>1363</b>  •  Dream Destiny WhatsApp Concierge: <b>Live Support</b>"
    )
    emerg_table = Table([[Paragraph(emerg_txt, style_card_meta)]], colWidths=[523])
    emerg_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#F59E0B")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(emerg_table)

    # Build document in memory
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
