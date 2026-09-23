"""
Dream Destiny - Manual Test Client
===================================
Edit the TRIP_REQUEST block below and run:

    python test_plan.py

Make sure all 6 services are running first:
  Port 8000 - planner-service  (uvicorn main:app --port 8000)
  Port 8001 - tourism-service  (uvicorn main:app --port 8001)
  Port 8002 - hotel-service    (uvicorn app.main:app --port 8002)
  Port 8003 - route-service    (uvicorn app.main:app --port 8003)
  Port 8004 - bus-service      (uvicorn app.main:app --port 8004)
  Port 8005 - train-service    (uvicorn app.main:app --port 8005)
"""

import json
import time
import urllib.request
import urllib.error


# ==============================================================================
# EDIT THIS BLOCK TO CHANGE YOUR TEST INPUT
# ==============================================================================

TRIP_REQUEST = {
    "origin": "Chennai",
    "destination": "Coimbatore",
    "start_date": "2026-10-15",
    "end_date": "2026-10-18",
    "travelers": 2,

    "preferences": {

        # Budget level: "low" | "medium" | "high"
        "budget": {
            "level": "medium"
        },

        # Transport mode : "train" | "bus" | "flight" | "any"
        # Berth/class    : "1A" (First AC) | "2A" (Second AC) | "3A" (Third AC) | "CC" (Chair Car)
        #                  "SL" (Sleeper)  | "2S" (Second Sitting) | "GN" (General)
        #                  "any" or null   -> show all available classes
        "transport": {
            "mode": "train",
            "berth_preference": "3A"
        },

        # Hotel category: "budget" | "mid_range" | "luxury" | "any"
        "hotel": {
            "category": "mid_range"
        },

        # Travel pace: "relaxed" | "moderate" | "intensive"
        "activities": {
            "pace": "moderate",
            "interests": ["history", "nature"],
            "family_friendly": None,
            "accessibility": None,
        },

        # Food preferences (optional - uncomment if needed)
        # "food": {
        #     "dietary_restrictions": "none",   # "none"|"vegetarian"|"vegan"|"halal"|"gluten_free"
        #     "cuisines": ["South Indian"],
        #     "avoid_street_food": False
        # }
    }
}

# ==============================================================================
# WHICH ENDPOINT TO HIT
# ==============================================================================

# POST /plan         -> Full AI itinerary (Gemini 2.5 Flash decides everything)
# POST /plan/context -> Raw aggregated data only (no LLM, instant)
ENDPOINT = "http://localhost:8000/plan"
#ENDPOINT = "http://localhost:8000/plan/context"

# ==============================================================================


def call_api(endpoint, body):
    data = json.dumps(body, default=str).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_transport_block(label, t):
    if not t:
        return
    print()
    print("  " + label)
    if t.get("mode") == "train":
        print("    %s - %s" % (t.get("train_number", "?"), t.get("train_name", "?")))
        print("    Departs %s @ %s" % (t.get("departure_date", ""), t.get("departure_time", "?")))
        print("    Arrives %s @ %s" % (t.get("arrival_date", ""), t.get("arrival_time", "?")))
        print("    Class: %s | Seats: %s %s | Rs.%s/person" % (
            t.get("travel_class", "?"),
            t.get("seats_available", "?"),
            t.get("seat_status", ""),
            t.get("fare_per_person", "?")
        ))
    else:
        print("    %s - %s" % (t.get("operator_name", "?"), t.get("bus_type", "?")))
        print("    Departs @ %s | Arrives @ %s" % (
            t.get("departure_time", "?"), t.get("arrival_time", "?")))
        print("    Seats: %s | Rs.%s/person" % (
            t.get("seats_available", "?"), t.get("fare_per_person", "?")))
    if t.get("reasoning"):
        print("    Reason: %s" % t.get("reasoning"))


def print_itinerary(res):
    s = res.get("summary", {})
    print()
    print("=" * 65)
    print("  TRIP: %s -> %s" % (s.get("origin"), s.get("destination")))
    print("  Days: %s  |  Travelers: %s" % (s.get("days"), s.get("travelers")))
    print("  Pace: %s  |  Budget: %s" % (s.get("pace"), s.get("budget_level")))
    print("=" * 65)

    hotel = res.get("hotel")
    if hotel:
        print()
        print("  HOTEL SELECTED")
        print("    Name   : %s" % hotel.get("hotel_name"))
        print("    ID     : %s" % hotel.get("hotel_id"))
        if hotel.get("reasoning"):
            print("    Reason : %s" % hotel.get("reasoning"))

    ob = res.get("outbound_transport")
    print_transport_block(
        "OUTBOUND TRANSPORT (%s)" % (ob.get("leg", "") if ob else ""),
        ob
    )

    rb = res.get("return_transport")
    print_transport_block(
        "RETURN TRANSPORT (%s)" % (rb.get("leg", "") if rb else ""),
        rb
    )

    print()
    print("  DAY-BY-DAY ITINERARY")
    for day in res.get("days", []):
        date_str = "(%s)" % day.get("date", "") if day.get("date") else ""
        theme = day.get("theme") or ""
        print()
        print("  -- Day %d %s  %s" % (day["day"], date_str, theme))
        for act in day.get("activities", []):
            t = act.get("start_time") or "--:--"
            d = act.get("duration_minutes")
            dur = "%dmin" % d if d else "?"
            print("       %s  %s  (%s)" % (t, act["attraction_name"], dur))
            if act.get("notes"):
                print("             -> %s" % act["notes"])
        for leg in day.get("transport", []):
            print("       [TRANSPORT] %s - %s" % (leg.get("mode"), leg.get("leg", "")))

    notes = res.get("planning_notes")
    if notes:
        print()
        print("  PLANNING NOTES")
        print("    %s" % notes)

    print()
    print("=" * 65)
    print()


def print_context(res):
    ctx = res.get("context", res)
    status = ctx.get("service_status", {})
    print()
    print("=" * 65)
    print("  RAW TRIP CONTEXT  (no LLM)")
    print("=" * 65)
    print("  Service status : %s" % status)
    print("  Attractions    : %d" % len(ctx.get("attractions", [])))
    print("  Hotels         : %d" % len(ctx.get("hotels", [])))
    print("  Outbound trains: %d" % len(ctx.get("outbound_trains", [])))
    print("  Return  trains : %d" % len(ctx.get("return_trains", [])))
    print("  Outbound buses : %d" % len(ctx.get("outbound_buses", [])))
    print("  Return  buses  : %d" % len(ctx.get("return_buses", [])))
    route = ctx.get("route")
    if route:
        print("  Route distance : %s km" % route.get("distance_km"))
        for r in route.get("routes", []):
            print("    %-12s -> %s min" % (r.get("mode"), r.get("duration_minutes")))
    print()
    print("  Top Attractions:")
    for a in ctx.get("attractions", [])[:5]:
        print("    %s*  %s" % (a.get("rating", "?"), a.get("name")))
    print()
    print("  Top Hotels:")
    for h in ctx.get("hotels", [])[:5]:
        price = h.get("price", {}).get("per_night")
        price_str = "Rs.%s/night" % price if price else "price N/A"
        print("    %s*  %s  (%s)" % (h.get("rating", "?"), h.get("name"), price_str))
    print()


def main():
    transport = TRIP_REQUEST["preferences"]["transport"]
    activities = TRIP_REQUEST["preferences"]["activities"]
    print()
    print("Endpoint : %s" % ENDPOINT)
    print("Request  : %s -> %s" % (TRIP_REQUEST["origin"], TRIP_REQUEST["destination"]))
    print("Dates    : %s to %s" % (TRIP_REQUEST["start_date"], TRIP_REQUEST["end_date"]))
    print("Travelers: %d" % TRIP_REQUEST["travelers"])
    print("Mode     : %s" % transport.get("mode"))
    print("Berth    : %s" % transport.get("berth_preference", "any (not set)"))
    print("Pace     : %s" % activities.get("pace"))
    print("Interests: %s" % activities.get("interests"))
    print()
    print("Calling API (this may take 20-40s for /plan with LLM)...")

    t0 = time.time()
    try:
        res = call_api(ENDPOINT, TRIP_REQUEST)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print("\n  HTTP %d Error: %s" % (e.code, body))
        return
    except urllib.error.URLError as e:
        print("\n  Connection error: %s" % e.reason)
        print("  Are all 6 services running?")
        return
    elapsed = time.time() - t0

    print("Done in %.1fs" % elapsed)

    if "context" in ENDPOINT or res.get("context"):
        print_context(res)
    else:
        print_itinerary(res)

    dump = input("Dump full JSON? (y/N): ").strip().lower()
    if dump == "y":
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
