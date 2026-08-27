import json, sys
sys.path.insert(0, '.')

from app.schemas.context import (
    TripContext, AttractionContext, HotelContext, HotelPriceContext,
    TrainContext, TravelClassContext, BusContext, RouteContext, RouteModeContext, ServiceStatus
)
from app.schemas.request import (
    TripRequest, TripPreferences, BudgetPreferences,
    TransportPreferences, HotelPreferences, ActivityPreferences
)
from datetime import date

N_ATTRACTIONS   = 12
N_HOTELS        = 20
N_OUTB_TRAINS   = 16
N_RET_TRAINS    = 21
N_OUTB_BUSES    = 10
N_RET_BUSES     = 10

trip = TripRequest(
    origin="Chennai", destination="Coimbatore",
    start_date=date(2026,8,29), end_date=date(2026,8,31),
    travelers=2,
    preferences=TripPreferences(
        budget=BudgetPreferences(level="medium"),
        transport=TransportPreferences(mode="train"),
        hotel=HotelPreferences(category="mid_range"),
        activities=ActivityPreferences(pace="moderate", interests=["history","nature"])
    )
)

attractions = [
    AttractionContext(name="Attraction %d" % i, address="%d Main St" % i, rating=4.2,
                      review_count=500, latitude=11.0+i*0.01, longitude=76.9+i*0.01,
                      types=["tourist_attraction"])
    for i in range(N_ATTRACTIONS)
]

hotels = [
    HotelContext(id="hotel_%d" % i, name="Hotel %d" % i, rating=4.0+i*0.1, hotel_class=3,
                 price=HotelPriceContext(per_night=2000+i*500, total=4000+i*1000, currency="INR"),
                 amenities=["WiFi","Breakfast","Pool"])
    for i in range(N_HOTELS)
]

def make_train(i):
    return TrainContext(
        train_number="1267%d" % i, train_name="Express %d" % i, train_type="SF",
        departure_time="07:00", arrival_time="13:00",
        duration_minutes=360, duration="6h 00m", distance_km=507,
        lowest_fare=350+i*50, rating=4.0+i*0.05, has_pantry=True,
        running_days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        classes=[TravelClassContext(travel_class="SL", fare=350, availability="AVL 45", bookable=True)]
    )

def make_bus(i):
    return BusContext(
        operator_name="Bus Operator %d" % i, bus_type="AC Sleeper",
        departure_time="21:00", arrival_time="05:00",
        duration="8h 00m", duration_minutes=480,
        minimum_fare=600+i*50, rating=3.8+i*0.1
    )

context = TripContext(
    trip=trip,
    attractions=attractions,
    hotels=hotels,
    outbound_trains=[make_train(i) for i in range(N_OUTB_TRAINS)],
    return_trains=[make_train(i) for i in range(N_RET_TRAINS)],
    outbound_buses=[make_bus(i) for i in range(N_OUTB_BUSES)],
    return_buses=[make_bus(i) for i in range(N_RET_BUSES)],
    route=RouteContext(
        origin="Chennai", destination="Coimbatore", distance_km=508.34,
        routes=[RouteModeContext(mode="driving", duration_minutes=536),
                RouteModeContext(mode="transit", duration_minutes=485)]
    ),
    service_status=ServiceStatus(tourism=True, hotels=True, buses=True, trains=True, route=True)
)

from app.agents.planning_agent import _build_context_payload
from app.services.llm.prompts import PLANNING_SYSTEM_PROMPT

payload = _build_context_payload(context)
payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

def tokens(s):
    return len(s) // 4

print("=" * 60)
print("  WHAT IS SENT TO GEMINI — FULL BREAKDOWN")
print("=" * 60)
print()
print("Item counts in payload:")
print("  Attractions    :", len(payload["attractions"]))
print("  Hotels         :", len(payload["hotels"]))
print("  Outbound trains:", len(payload["outbound_trains"]))
print("  Return  trains :", len(payload["return_trains"]))
print("  Outbound buses :", len(payload["outbound_buses"]))
print("  Return  buses  :", len(payload["return_buses"]))
print()

a_tok  = sum(tokens(json.dumps(x)) for x in payload["attractions"])
h_tok  = sum(tokens(json.dumps(x)) for x in payload["hotels"])
ot_tok = sum(tokens(json.dumps(x)) for x in payload["outbound_trains"])
rt_tok = sum(tokens(json.dumps(x)) for x in payload["return_trains"])
ob_tok = sum(tokens(json.dumps(x)) for x in payload["outbound_buses"])
rb_tok = sum(tokens(json.dumps(x)) for x in payload["return_buses"])
tr_tok = tokens(json.dumps(payload["trip"]))
ro_tok = tokens(json.dumps(payload.get("route", {})))
sys_tok = tokens(PLANNING_SYSTEM_PROMPT)

total_data = tr_tok + a_tok + h_tok + ot_tok + rt_tok + ob_tok + rb_tok + ro_tok
grand_total = total_data + sys_tok

print("Token cost per section (approx, 4 chars = 1 token):")
print("  trip block          : ~%d tokens" % tr_tok)
print("  route block         : ~%d tokens" % ro_tok)
print("  %2d attractions      : ~%d tokens" % (N_ATTRACTIONS, a_tok))
print("  %2d hotels           : ~%d tokens" % (N_HOTELS, h_tok))
print("  %2d outbound trains  : ~%d tokens" % (N_OUTB_TRAINS, ot_tok))
print("  %2d return  trains   : ~%d tokens" % (N_RET_TRAINS, rt_tok))
print("  %2d outbound buses   : ~%d tokens" % (N_OUTB_BUSES, ob_tok))
print("  %2d return  buses    : ~%d tokens" % (N_RET_BUSES, rb_tok))
print("  ---")
print("  User data subtotal  : ~%d tokens" % total_data)
print("  System prompt       : ~%d tokens" % sys_tok)
print("  GRAND TOTAL INPUT   : ~%d tokens" % grand_total)
print()
print("Per-item sizes:")
print("  1 attraction  : ~%d tokens" % tokens(json.dumps(payload["attractions"][0])))
print("  1 hotel       : ~%d tokens" % tokens(json.dumps(payload["hotels"][0])))
print("  1 train       : ~%d tokens" % tokens(json.dumps(payload["outbound_trains"][0])))
print("  1 bus         : ~%d tokens" % tokens(json.dumps(payload["outbound_buses"][0])))
print()
print("Fields included per domain (sent to LLM):")
print("  Attractions :", list(payload["attractions"][0].keys()))
print("  Hotels      :", list(payload["hotels"][0].keys()))
print("  Trains      :", list(payload["outbound_trains"][0].keys()))
print("  Buses       :", list(payload["outbound_buses"][0].keys()))
print()
print("Fields stripped (NOT sent to LLM):")
print("  Hotel  : description, check_in_time, check_out_time,")
print("           nearby_places, image_url, website_url, review_count")
print("  Train  : train_type, distance_km, classes[], recommended_class")
print("  Bus    : boarding_point, dropping_point, available_seats, max_fare")
print("  Attr   : google_maps_url, image_url")
print()
print("=" * 60)
print("The BIGGEST token consumers:")
print("  Hotels (%d x ~%d tok) = ~%d tokens — hotel amenities lists inflate this" % (
    N_HOTELS, tokens(json.dumps(payload["hotels"][0])), h_tok))
print("  Trains (%d + %d = %d total, ~%d tok) = ~%d tokens — running_days[] is expensive" % (
    N_OUTB_TRAINS, N_RET_TRAINS, N_OUTB_TRAINS+N_RET_TRAINS,
    tokens(json.dumps(payload["outbound_trains"][0])),
    ot_tok+rt_tok))
print("=" * 60)
