from app.whatsapp.messages import format_itinerary_message


def test_hotel_price_balance_and_arrival_directions_are_visible():
    itinerary = {
        "summary": {"origin": "Chennai", "destination": "Hyderabad", "days": 2,
                    "travelers": 1, "pace": "moderate", "budget_level": "low"},
        "hotel": {"hotel_name": "Central Hotel", "price_per_night": 1400,
                  "price_total": 2800, "rating": 4.4, "review_count": 600,
                  "reasoning": "20 min average drive to planned sights"},
        "arrival_to_hotel": {"from_name": "Hyderabad Deccan Railway Station",
            "to_hotel": "Central Hotel", "travel_minutes": 18,
            "instruction": "Take a taxi or auto from Hyderabad Deccan Railway Station to Central Hotel; about 18 min by road.",
            "maps_url": "https://www.google.com/maps/dir/?api=1"},
        "days": [],
    }
    text = format_itinerary_message(itinerary, "Chennai", "Hyderabad")
    assert "Central Hotel" in text
    assert "₹1,400/night" in text
    assert "4.4/5 (600 reviews)" in text
    assert "AFTER ARRIVING IN THE CITY" in text
    assert "18 min by road" in text
    assert "https://www.google.com/maps/dir/" in text
