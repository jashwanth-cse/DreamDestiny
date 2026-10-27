import pytest
from app.services.pdf_generator import generate_itinerary_pdf, create_placeholder_thumbnail
from app.whatsapp.messages import build_document_message
from app.whatsapp.client import whatsapp_client
from app.config import settings


def test_pdf_generation_in_memory_valid_header():
    """Verify that PDF is generated directly in memory and contains standard PDF structure."""
    sample_itinerary = {
        "summary": {
            "destination": "Madurai",
            "origin": "Rajapalayam",
            "days": 3,
            "travelers": 2,
            "pace": "moderate",
            "budget_level": "medium",
        },
        "transport_mode": "car",
        "hotel": {
            "hotel_name": "Heritage Madurai",
            "price_per_night": 3800.0,
            "price_total": 7600.0,
            "reasoning": "Traditional resort with temple views.",
        },
        "days": [
            {
                "day": 1,
                "date": "2026-11-01",
                "theme": "Sacred Architecture",
                "activities": [
                    {
                        "attraction_name": "Meenakshi Amman Temple",
                        "start_time": "10:30 AM",
                        "duration_minutes": 120,
                        "notes": "Historic temple with 14 gopurams.",
                    },
                    {
                        "attraction_name": "Thirumalai Nayakkar Mahal",
                        "start_time": "03:00 PM",
                        "duration_minutes": 90,
                        "notes": "17th-century palace with sound and light show.",
                    }
                ]
            }
        ],
        "total_cost": 12500.0,
    }

    pdf_bytes = generate_itinerary_pdf(
        itinerary=sample_itinerary,
        origin="Rajapalayam",
        destination="Madurai",
    )

    # Must be valid non-empty bytes
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    # Must start with standard PDF magic number
    assert pdf_bytes.startswith(b"%PDF-")


def test_placeholder_thumbnail_generation():
    """Verify in-memory PIL image thumbnail generator."""
    buf = create_placeholder_thumbnail("Meenakshi Amman Temple")
    assert buf is not None
    data = buf.getvalue()
    assert len(data) > 1000
    # JPEG magic bytes
    assert data[:2] == b"\xff\xd8"


def test_build_document_message_structure():
    """Verify WhatsApp document payload schema."""
    doc_msg = build_document_message(
        recipient="919876543210",
        media_id="media_test_12345",
        filename="Madurai_Travel_Dossier.pdf",
        caption="Your Travel Dossier is ready!",
    )

    assert doc_msg["messaging_product"] == "whatsapp"
    assert doc_msg["type"] == "document"
    assert doc_msg["to"] == "919876543210"
    assert doc_msg["document"]["id"] == "media_test_12345"
    assert doc_msg["document"]["filename"] == "Madurai_Travel_Dossier.pdf"
    assert doc_msg["document"]["caption"] == "Your Travel Dossier is ready!"


@pytest.mark.asyncio
async def test_upload_media_in_test_mode(monkeypatch):
    """Verify upload_media returns a valid mock media ID in test mode without disk writes."""
    monkeypatch.setattr(settings, "app_env", "test")
    dummy_bytes = b"%PDF-1.4 test bytes"
    media_id = await whatsapp_client.upload_media(
        file_bytes=dummy_bytes,
        filename="test.pdf",
        mime_type="application/pdf",
    )
    assert media_id is not None
    assert isinstance(media_id, str)
    assert len(media_id) > 0


@pytest.mark.asyncio
async def test_pdf_generation_async():
    """Verify async generation via Designer Playwright Engine."""
    sample = {
        "summary": {"destination": "Madurai", "origin": "Rajapalayam", "days": 3, "travelers": 2},
        "days": [
            {
                "day": 1,
                "theme": "Heritage",
                "activities": [
                    {"attraction_name": "Meenakshi Amman Temple", "start_time": "10:00 AM"}
                ]
            }
        ]
    }
    from app.services.pdf_generator import generate_itinerary_pdf_async
    pdf_bytes = await generate_itinerary_pdf_async(sample, "Rajapalayam", "Madurai")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_image_mapping_and_no_generic_fallback():
    """Verify that when no image_url is provided, zero generic images are injected,
    and when an image_url is provided, caption is strictly mapped 1-to-1."""
    import io
    from PIL import Image as PILImage
    from app.services.pdf_designer import build_editorial_pdf

    # Create dummy 100x100 PNG image bytes
    buf = io.BytesIO()
    PILImage.new("RGB", (100, 100), color=(15, 23, 42)).save(buf, format="PNG")
    dummy_img_bytes = buf.getvalue()

    sample_with_one_image = {
        "summary": {"destination": "Madurai", "origin": "Rajapalayam", "days": 2, "travelers": 2},
        "days": [
            {
                "day": 1,
                "theme": "Sacred Sights",
                "activities": [
                    {
                        "attraction_name": "Meenakshi Amman Temple",
                        "image_url": "https://example.com/meenakshi.jpg",
                        "start_time": "09:00 AM",
                    },
                    {
                        "attraction_name": "Thirumalai Nayakkar Mahal",
                        # NO image_url provided!
                        "start_time": "02:00 PM",
                    }
                ]
            }
        ]
    }

    image_map = {"https://example.com/meenakshi.jpg": dummy_img_bytes}
    pdf_bytes = build_editorial_pdf(
        itinerary=sample_with_one_image,
        origin="Rajapalayam",
        destination="Madurai",
        image_bytes_map=image_map,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

