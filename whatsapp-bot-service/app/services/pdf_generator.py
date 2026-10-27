"""
Unified PDF Travel Dossier Generator.
Routes generation to the high-res Designer PDF Engine (Playwright Headless Chromium)
with a robust fallback to ReportLab.
Guarantees ZERO files are saved to disk.
"""

import io
import asyncio
import logging
from typing import Dict, Any, Optional

from app.services.pdf_designer import render_designer_pdf

logger = logging.getLogger(__name__)


def create_placeholder_thumbnail(attraction_name: str, category: str = "") -> io.BytesIO:
    """Thumbnail generator for backward compatibility."""
    from PIL import Image as PILImage, ImageDraw
    w, h = 360, 240
    img = PILImage.new("RGB", (w, h), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, w - 8, h - 8], outline=(13, 148, 136), width=2)
    draw.text((20, 100), attraction_name[:25], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


async def generate_itinerary_pdf_async(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Async generation using the Designer Playwright Engine."""
    try:
        return await render_designer_pdf(itinerary, origin, destination, trip_meta)
    except Exception as exc:
        logger.warning("Designer PDF rendering fallback to ReportLab: %s", exc)
        return _fallback_reportlab_pdf(itinerary, origin, destination, trip_meta)


def generate_itinerary_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Synchronous / universal entry point for generating the PDF Travel Dossier in memory.
    If an event loop is running, schedules on the loop or runs synchronously.
    """
    try:
        try:
            return asyncio.run(render_designer_pdf(itinerary, origin, destination, trip_meta))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, render_designer_pdf(itinerary, origin, destination, trip_meta))
                return future.result(timeout=15)
    except Exception as exc:
        logger.warning("Playwright render error, using fallback ReportLab PDF: %s", exc)
        return _fallback_reportlab_pdf(itinerary, origin, destination, trip_meta)


def _fallback_reportlab_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Graceful in-memory fallback using ReportLab if Chromium is ever disabled."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    orig_title = origin.strip().title()
    dest_title = destination.strip().title()

    story = [
        Paragraph(f"<b>DREAM DESTINY ✦ {orig_title.upper()} ➔ {dest_title.upper()}</b>", styles["Title"]),
        Spacer(1, 10),
        Paragraph("<b>EXECUTIVE TRAVEL DOSSIER & ITINERARY</b>", styles["Heading2"]),
        Spacer(1, 14),
    ]

    days = itinerary.get("days") or itinerary.get("itinerary") or []
    for d in days:
        if isinstance(d, dict):
            story.append(Paragraph(f"<b>Day {d.get('day', 1)}: {d.get('theme', 'Sightseeing')}</b>", styles["Heading3"]))
            for act in d.get("activities") or d.get("schedule") or []:
                if isinstance(act, dict):
                    name = act.get("attraction_name") or act.get("name") or "Activity"
                    t = act.get("start_time") or ""
                    story.append(Paragraph(f"• {name}  —  {t}", styles["Normal"]))
            story.append(Spacer(1, 10))

    doc.build(story)
    return buf.getvalue()
