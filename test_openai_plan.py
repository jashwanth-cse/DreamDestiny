"""
Dream Destiny — OpenAI / GPT Travel Planner Test Script
=============================================================
Standalone script to test itinerary generation with OpenAI models (e.g. gpt-4o-mini, gpt-4o).

Run with:
    python test_openai_plan.py
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Model name: "gpt-4o-mini", "gpt-4o", "o3-mini", etc.
MODEL = "gpt-4o-mini"

# Endpoint:
# "https://api.openai.com/v1/responses"        (New Responses API)
# "https://api.openai.com/v1/chat/completions" (Standard Chat Completions API)
ENDPOINT = "https://api.openai.com/v1/responses"

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD API KEY FROM .env IF NOT ALREADY SET
# ═══════════════════════════════════════════════════════════════════════════════

if not OPENAI_API_KEY:
    for env_path in [".env", "planner-service/.env"]:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        OPENAI_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if OPENAI_API_KEY:
            break

# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLE PRE-FILTERED TRIP CONTEXT (REAL DATA STRUCTURE)
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_TRIP_PAYLOAD = {
    "trip": {
        "origin": "Chennai",
        "destination": "Coimbatore",
        "start_date": "2026-08-29",
        "end_date": "2026-08-31",
        "days": 2,
        "travelers": 2,
        "preferences": {
            "budget": "medium",
            "transport_mode": "train",
            "berth_preference": "3A",
            "hotel_category": "mid_range",
            "pace": "moderate",
            "interests": ["history", "nature"],
            "family_friendly": None,
            "food": None
        }
    },
    "attractions": [
        {
            "name": "TNAU Botanical Garden",
            "address": "Lawley Road, Coimbatore",
            "rating": 4.5,
            "review_count": 8200,
            "latitude": 11.0134,
            "longitude": 76.9348,
            "types": ["tourist_attraction", "park"]
        },
        {
            "name": "Gass Forest Museum",
            "address": "Forest College Campus, RS Puram, Coimbatore",
            "rating": 4.4,
            "review_count": 3100,
            "latitude": 11.0185,
            "longitude": 76.9452,
            "types": ["tourist_attraction", "museum"]
        },
        {
            "name": "Clock Tower - DB Road, RS Puram",
            "address": "DB Road, RS Puram, Coimbatore",
            "rating": 4.2,
            "review_count": 950,
            "latitude": 11.0102,
            "longitude": 76.9495,
            "types": ["tourist_attraction", "point_of_interest"]
        },
        {
            "name": "Gedee Car Museum",
            "address": "Avanashi Road, Race Course, Coimbatore",
            "rating": 4.7,
            "review_count": 14200,
            "latitude": 11.0025,
            "longitude": 76.9782,
            "types": ["tourist_attraction", "museum"]
        },
        {
            "name": "Sri Arulmigu Mundhi Vinayagar Temple",
            "address": "Puliakulam, Coimbatore",
            "rating": 4.8,
            "review_count": 6800,
            "latitude": 11.0051,
            "longitude": 76.9950,
            "types": ["place_of_worship", "hindu_temple"]
        },
        {
            "name": "Race Course - Zone 2",
            "address": "Race Course Road, Gopalapuram, Coimbatore",
            "rating": 4.6,
            "review_count": 5400,
            "latitude": 11.0010,
            "longitude": 76.9740,
            "types": ["tourist_attraction", "park"]
        },
        {
            "name": "Smart City Coimbatore Valankulam",
            "address": "Sungam Bypass, Valankulam, Coimbatore",
            "rating": 4.3,
            "review_count": 4200,
            "latitude": 10.9940,
            "longitude": 76.9720,
            "types": ["tourist_attraction", "park"]
        },
        {
            "name": "Valankulam Boat House",
            "address": "Valankulam Lake Promenade, Coimbatore",
            "rating": 4.3,
            "review_count": 2800,
            "latitude": 10.9930,
            "longitude": 76.9710,
            "types": ["tourist_attraction", "point_of_interest"]
        },
        {
            "name": "Marudamalai Murugan Temple",
            "address": "Marudamalai Hill, Coimbatore",
            "rating": 4.8,
            "review_count": 22000,
            "latitude": 11.0456,
            "longitude": 76.8521,
            "types": ["place_of_worship", "hindu_temple"]
        },
        {
            "name": "Selvachinthamani Kulam",
            "address": "Selvachinthamani Lake, Coimbatore",
            "rating": 4.2,
            "review_count": 1100,
            "latitude": 10.9980,
            "longitude": 76.9530,
            "types": ["tourist_attraction", "natural_feature"]
        }
    ],
    "hotels": [
        {
            "id": "hotel_windstone_residency",
            "name": "Windstone Residency",
            "rating": 4.6,
            "hotel_class": 3,
            "price_per_night": 2400.0,
            "price_total": 4800.0,
            "currency": "INR",
            "amenities": ["Free WiFi", "Breakfast included", "Room service", "Air conditioning"]
        },
        {
            "id": "hotel_crystal_lake_suites",
            "name": "Crystal Lake Suites, Coimbatore",
            "rating": 4.7,
            "hotel_class": 3,
            "price_per_night": 2800.0,
            "price_total": 5600.0,
            "currency": "INR",
            "amenities": ["Free WiFi", "Lake view", "Restaurant", "Air conditioning"]
        },
        {
            "id": "hotel_treebo_vinayak_inn",
            "name": "Treebo Vinayak Inn",
            "rating": 4.4,
            "hotel_class": 3,
            "price_per_night": 1900.0,
            "price_total": 3800.0,
            "currency": "INR",
            "amenities": ["Free WiFi", "Air conditioning", "Elevator"]
        }
    ],
    "outbound_trains": [
        {
            "train_number": "12675",
            "train_name": "KOVAI SF EXP",
            "departure_date": "2026-08-29",
            "departure_time": "07:35",
            "arrival_date": "2026-08-29",
            "arrival_time": "13:45",
            "duration": "6h 10m",
            "distance_km": 497,
            "has_pantry": True,
            "rating": 4.4,
            "travel_class": "3A",
            "fare_per_person": 1000,
            "seat_status": "AVL",
            "seats_available": 74
        },
        {
            "train_number": "12671",
            "train_name": "NILAGIRI SF EXP",
            "departure_date": "2026-08-28",
            "departure_time": "21:05",
            "arrival_date": "2026-08-29",
            "arrival_time": "05:10",
            "duration": "8h 05m",
            "distance_km": 497,
            "has_pantry": True,
            "rating": 4.5,
            "travel_class": "3A",
            "fare_per_person": 1050,
            "seat_status": "AVL",
            "seats_available": 42
        }
    ],
    "return_trains": [
        {
            "train_number": "12676",
            "train_name": "KOVAI SF EXP",
            "departure_date": "2026-08-31",
            "departure_time": "14:45",
            "arrival_date": "2026-08-31",
            "arrival_time": "21:00",
            "duration": "6h 15m",
            "distance_km": 497,
            "has_pantry": True,
            "rating": 4.3,
            "travel_class": "3A",
            "fare_per_person": 1000,
            "seat_status": "AVL",
            "seats_available": 82
        },
        {
            "train_number": "12672",
            "train_name": "NILAGIRI SF EXP",
            "departure_date": "2026-08-31",
            "departure_time": "22:15",
            "arrival_date": "2026-09-01",
            "arrival_time": "06:20",
            "duration": "8h 05m",
            "distance_km": 497,
            "has_pantry": True,
            "rating": 4.4,
            "travel_class": "3A",
            "fare_per_person": 1050,
            "seat_status": "AVL",
            "seats_available": 35
        }
    ],
    "outbound_buses": [
        {
            "operator_name": "THAMARAI BUS TRANSPORTS",
            "bus_type": "Bharat Benz A/C Sleeper (2+1)",
            "departure_time": "21:00",
            "arrival_time": "06:00",
            "duration": "9h 00m",
            "minimum_fare": 1209.0,
            "available_seats": 30,
            "rating": 4.6
        }
    ],
    "return_buses": [
        {
            "operator_name": "THAMARAI BUS TRANSPORTS",
            "bus_type": "Bharat Benz A/C Sleeper (2+1)",
            "departure_time": "20:30",
            "arrival_time": "05:30",
            "duration": "9h 00m",
            "minimum_fare": 1459.0,
            "available_seats": 33,
            "rating": 4.6
        }
    ],
    "route": {
        "distance_km": 508.34,
        "modes": [
            {"mode": "driving", "duration_minutes": 536},
            {"mode": "transit", "duration_minutes": 485}
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT & SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

try:
    sys.path.insert(0, "planner-service")
    from app.services.llm.prompts import PLANNING_SYSTEM_PROMPT
    from app.schemas.itinerary import Itinerary
    ITINERARY_SCHEMA = Itinerary.model_json_schema()
except Exception:
    PLANNING_SYSTEM_PROMPT = """
You are an expert travel itinerary planner for Indian destinations.
Produce a practical, day-by-day trip plan using ONLY supplied data.

RULES:
1. Use ONLY data present in TripContext. Copy transport fields EXACTLY.
2. Reference hotels by exact "id" and "name".
3. Reference attractions by exact "name".
4. Always prefer seat_status="AVL" over "RAC".
5. Return ONLY a valid JSON object matching the Itinerary schema.
""".strip()
    ITINERARY_SCHEMA = None


def make_openai_request(endpoint, api_key, model, system_prompt, user_data):
    """
    Calls OpenAI API. In /v1/responses, the JSON schema/object parameter is under `text.format`.
    In /v1/chat/completions, it is under `response_format`.
    """
    user_content = (
        "Here is the TripContext for this planning request:\n\n"
        + json.dumps(user_data, ensure_ascii=False, indent=2)
        + "\n\nProduce the Itinerary JSON as specified."
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if "v1/responses" in endpoint:
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "text": {
                "format": {
                    "type": "json_object"
                }
            }
        }
    else:  # /v1/chat/completions
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_content_and_usage(raw_response):
    """
    Extracts text content and usage statistics from OpenAI response.
    """
    usage = raw_response.get("usage", {})

    # Responses API: output list
    if "output" in raw_response:
        output = raw_response["output"]
        if isinstance(output, str):
            return output, usage
        if isinstance(output, list):
            texts = []
            for item in output:
                if isinstance(item, dict):
                    # Check message content list
                    content = item.get("content", [])
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and "text" in c:
                                texts.append(c["text"])
                            elif isinstance(c, str):
                                texts.append(c)
                    elif isinstance(content, str):
                        texts.append(content)
                    elif "text" in item:
                        texts.append(item["text"])
            if texts:
                return "".join(texts), usage

    # Chat Completions API: choices list
    if "choices" in raw_response and len(raw_response["choices"]) > 0:
        choice = raw_response["choices"][0]
        text = choice.get("message", {}).get("content", "")
        return text, usage

    if "output_text" in raw_response:
        return raw_response["output_text"], usage

    raise ValueError(f"Unknown response format: {json.dumps(raw_response)[:300]}")


def print_itinerary(res):
    s = res.get("summary", {})
    print()
    print("=" * 65)
    print(f"  TRIP: {s.get('origin')} -> {s.get('destination')}")
    print(f"  Days: {s.get('days')}  |  Travelers: {s.get('travelers')}")
    print(f"  Pace: {s.get('pace')}  |  Budget: {s.get('budget_level')}")
    print("=" * 65)

    hotel = res.get("hotel")
    if hotel:
        print()
        print("  HOTEL SELECTED")
        print(f"    Name   : {hotel.get('hotel_name')}")
        print(f"    ID     : {hotel.get('hotel_id')}")
        if hotel.get("reasoning"):
            print(f"    Reason : {hotel.get('reasoning')}")

    def print_transport(label, t):
        if not t:
            return
        print()
        print(f"  {label}")
        if t.get("mode") == "train":
            print(f"    {t.get('train_number','?')} - {t.get('train_name','?')}")
            print(f"    Departs {t.get('departure_date','')} @ {t.get('departure_time','?')}")
            print(f"    Arrives {t.get('arrival_date','')} @ {t.get('arrival_time','?')}")
            print(f"    Class: {t.get('travel_class','?')} | Seats: {t.get('seats_available','?')} {t.get('seat_status','')} | Rs.{t.get('fare_per_person','?')}/person")
        else:
            print(f"    {t.get('operator_name','?')} - {t.get('bus_type','?')}")
            print(f"    Departs @ {t.get('departure_time','?')} | Arrives @ {t.get('arrival_time','?')}")
            print(f"    Seats: {t.get('seats_available','?')} | Rs.{t.get('fare_per_person','?')}/person")
        if t.get("reasoning"):
            print(f"    Reason: {t.get('reasoning')}")

    print_transport("OUTBOUND TRANSPORT", res.get("outbound_transport"))
    print_transport("RETURN TRANSPORT", res.get("return_transport"))

    print()
    print("  DAY-BY-DAY ITINERARY")
    for day in res.get("days", []):
        date_str = f"({day.get('date', '')})" if day.get("date") else ""
        theme = day.get("theme") or ""
        print()
        print(f"  -- Day {day['day']} {date_str}  {theme}")
        for act in day.get("activities", []):
            t = act.get("start_time") or "--:--"
            d = act.get("duration_minutes")
            dur = f"{d}min" if d else "?"
            print(f"       {t}  {act['attraction_name']}  ({dur})")
            if act.get("notes"):
                print(f"             -> {act['notes']}")
        for leg in day.get("transport", []):
            print(f"       [TRANSPORT] {leg.get('mode')} - {leg.get('leg', '')}")

    notes = res.get("planning_notes")
    if notes:
        print()
        print("  PLANNING NOTES")
        print(f"    {notes}")

    print()
    print("=" * 65)


def main():
    global OPENAI_API_KEY, ENDPOINT, MODEL

    print()
    print("=" * 65)
    print("  OpenAI / GPT Travel Planner Test")
    print("=" * 65)
    print(f"  Model    : {MODEL}")
    print(f"  Endpoint : {ENDPOINT}")

    if not OPENAI_API_KEY:
        print()
        OPENAI_API_KEY = input("Enter your OPENAI_API_KEY: ").strip()

    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY is required to test.")
        return

    print("\nCalling OpenAI API...")
    t0 = time.time()
    try:
        raw_res = make_openai_request(
            endpoint=ENDPOINT,
            api_key=OPENAI_API_KEY,
            model=MODEL,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            user_data=SAMPLE_TRIP_PAYLOAD,
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"\n  HTTP {e.code} Error on {ENDPOINT}:")
        print(f"  {body}")
        return
    except urllib.error.URLError as e:
        print(f"\n  Connection error: {e.reason}")
        return

    elapsed = time.time() - t0

    try:
        text, usage = extract_content_and_usage(raw_res)
        parsed_itinerary = json.loads(text)
    except Exception as exc:
        print(f"\nFailed to parse model output: {exc}")
        print("Raw response:", json.dumps(raw_res, indent=2)[:500])
        return

    print(f"\nResponse received in {elapsed:.2f}s")
    if usage:
        print(f"Tokens: Prompt={usage.get('prompt_tokens', usage.get('input_tokens', '?'))} | "
              f"Completion={usage.get('completion_tokens', usage.get('output_tokens', '?'))} | "
              f"Total={usage.get('total_tokens', '?')}")

    print_itinerary(parsed_itinerary)

    dump = input("\nDump full JSON? (y/N): ").strip().lower()
    if dump == "y":
        print(json.dumps(parsed_itinerary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
