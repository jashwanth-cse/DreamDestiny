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
    assert len(pdf_bytes) > 5000
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
