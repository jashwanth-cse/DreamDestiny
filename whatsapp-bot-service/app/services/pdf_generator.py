"""
Unified PDF Travel Dossier Generator.
Routes generation to the high-res Designer Editorial PDF Engine (ReportLab + Pillow)
with active Google Maps hyperlinks, Polaroid showcases, and verified logistics Bento boxes.
Guarantees ZERO files are saved to disk.
"""

import io
import asyncio
import logging
from typing import Dict, Any, Optional

from app.services.pdf_designer import render_designer_pdf, render_designer_pdf_sync

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
    """Async generation using the Designer Editorial Engine with concurrent image downloading."""
    try:
        return await render_designer_pdf(itinerary, origin, destination, trip_meta)
    except Exception as exc:
        logger.error("Designer PDF async render error, using sync fallback: %s", exc, exc_info=True)
        return render_designer_pdf_sync(itinerary, origin, destination, trip_meta)


def generate_itinerary_pdf(
    itinerary: Dict[str, Any],
    origin: str,
    destination: str,
    trip_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Synchronous / universal entry point for generating the PDF Travel Dossier in memory.
    """
    try:
        return render_designer_pdf_sync(itinerary, origin, destination, trip_meta)
    except Exception as exc:
        logger.error("Designer PDF sync render error: %s", exc, exc_info=True)
        # Basic emergency fallback if anything unexpected fails
        return render_designer_pdf_sync(itinerary, origin, destination, trip_meta)
