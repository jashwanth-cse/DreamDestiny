import pytest
from PIL import Image
import io

from app.services.itinerary_card_service import itinerary_card_service
from app.whatsapp.messages import build_image_message
from app.whatsapp.client import whatsapp_client


def test_itinerary_card_generation_full():
    """Verify card generation with complete trip payload."""
    payload = {
        "destination": "Goa",
        "origin": "Mumbai",
        "transport": {
            "mode": "train",
            "name": "Mandovi Express",
            "number": "10103",
            "departure": "07:10 AM",
            "arrival": "06:45 PM",
            "fare": 480,
        },
        "hotel": {
            "hotel_name": "Fairfield by Marriott",
            "rating": "4.4",
            "price_per_night": 4200,
            "price_total": 12600,
        },
        "days": [
            {
                "day": 1,
                "title": "North Goa Beaches",
                "date": "14 Nov",
                "activities": [
                    {"time": "10:00 AM", "attraction_name": "Calangute Beach"},
                    {"time": "05:00 PM", "attraction_name": "Curlies Shack"},
                ],
            },
            {
                "day": 2,
                "title": "Old Goa Heritage",
                "date": "15 Nov",
                "activities": [
                    {"time": "09:00 AM", "attraction_name": "Basilica of Bom Jesus"},
                ],
            },
        ],
    }

    card_bytes = itinerary_card_service.generate_card_bytes(
        itinerary_data=payload,
        origin="Mumbai",
        destination="Goa",
        days=2,
        travelers=2,
    )

    assert card_bytes is not None
    assert isinstance(card_bytes, bytes)
    assert card_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify Pillow can open and verify dimensions
    img = Image.open(io.BytesIO(card_bytes))
    assert img.size[0] == 1080
    assert img.size[1] >= 1500


def test_itinerary_card_generation_minimal():
    """Verify card generation is fault tolerant with minimal or empty payload."""
    empty_payload = {}
    card_bytes = itinerary_card_service.generate_card_bytes(
        itinerary_data=empty_payload,
        origin="Delhi",
        destination="Manali",
        days=3,
        travelers=1,
    )

    assert card_bytes is not None
    assert isinstance(card_bytes, bytes)
    assert card_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_build_image_message_payload():
    """Verify build_image_message creates valid WhatsApp Cloud API schema."""
    msg = build_image_message(
        recipient="919876543210",
        media_id="media_123456",
        caption="Your 3-Day Goa Itinerary",
    )

    assert msg["messaging_product"] == "whatsapp"
    assert msg["to"] == "919876543210"
    assert msg["type"] == "image"
    assert msg["image"]["id"] == "media_123456"
    assert msg["image"]["caption"] == "Your 3-Day Goa Itinerary"


@pytest.mark.asyncio
async def test_whatsapp_client_upload_media_mock():
    """Verify WhatsApp client media upload behavior."""
    test_bytes = b"fake-png-bytes"
    media_id = await whatsapp_client.upload_media(
        file_bytes=test_bytes,
        filename="test.png",
        mime_type="image/png",
    )
    assert media_id is not None
    assert isinstance(media_id, str) and len(media_id) > 0
