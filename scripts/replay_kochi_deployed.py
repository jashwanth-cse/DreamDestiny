"""Replay the Rajapalayam–Kochi case against a deployed gateway.

Run: python scripts/replay_kochi_deployed.py --base https://dreamdestiny.duckdns.org
The script performs a real Bedrock /plan call and provider searches; it prints no keys.
"""

import argparse
import json
import sys
from datetime import date

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://dreamdestiny.duckdns.org")
    parser.add_argument("--start", default="2026-12-15")
    parser.add_argument("--end", default="2026-12-17")
    parser.add_argument("--expect-complete", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    trip = {"origin": "Rajapalayam", "destination": "Kochi",
            "start_date": args.start, "end_date": args.end, "travelers": 1,
            "preferences": {"budget": {"level": "medium"},
                            "transport": {"mode": "bus"},
                            "hotel": {"category": "any"},
                            "activities": {"pace": "moderate"}}}
    def call(client, method, path, **kwargs):
        try:
            response = client.request(method, base + path, **kwargs)
            try:
                data = response.json()
            except ValueError:
                data = {}
            print(f"{method} {path}: HTTP {response.status_code}")
            return response.status_code, data
        except httpx.RequestError as exc:
            print(f"{method} {path}: {type(exc).__name__}")
            return 0, {}

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for path in ("/health", "/hotels/health", "/tourism/health",
                     "/route/health", "/api/v1/buses/health",
                     "/api/v1/trains/health", "/plan/health"):
            call(client, "GET", path)
        hotel_status, hotel_data = call(client, "GET", "/hotels", params={
            "city": "Kochi", "check_in": args.start, "check_out": args.end,
            "adults": 1, "children": 0})
        print("  sourced hotels:", hotel_data.get("count", 0))
        call(client, "GET", "/tourism", params={"city": "Kochi", "limit": 12})
        call(client, "GET", "/route", params={"origin": "Rajapalayam", "destination": "Kochi"})
        for source, destination, day in (("Rajapalayam", "Kochi", args.start),
                                         ("Kochi", "Rajapalayam", args.end)):
            travel_date = date.fromisoformat(day).strftime("%d-%m-%Y")
            call(client, "GET", "/api/v1/buses/search", params={
                "source": source, "destination": destination, "journey_date": travel_date})
        call(client, "GET", "/api/v1/trains/search", params={
            "from": "Rajapalayam", "to": "Kochi",
            "date": date.fromisoformat(args.start).strftime("%d-%m-%Y")})
        _, envelope = call(client, "POST", "/plan/context", json=trip)
        context = envelope.get("context") or envelope
        print("  context hotels/buses/trains:", len(context.get("hotels", [])),
              len(context.get("outbound_buses", [])), len(context.get("return_buses", [])),
              len(context.get("outbound_trains", [])))
        plan_status, itinerary = call(client, "POST", "/plan", json=trip)
        hotel = itinerary.get("hotel") or {}
        outbound = itinerary.get("outbound_transport") or {}
        inbound = itinerary.get("return_transport") or {}
        print("  itinerary:", json.dumps({"hotel": hotel.get("hotel_name"),
              "rate": hotel.get("price_per_night"), "outbound": outbound.get("mode"),
              "return": inbound.get("mode"),
              "arrival_transfer": bool(itinerary.get("arrival_to_hotel")),
              "days": len(itinerary.get("days", []))}))
        correct = (plan_status == 200 and hotel_status == 200 and
                   bool(hotel.get("hotel_name")) and
                   outbound.get("mode") == "bus" and inbound.get("mode") == "bus" and
                   bool(itinerary.get("arrival_to_hotel")))
        safe_failure = plan_status in (409, 503) and not itinerary.get("outbound_transport")
        print("result:", "complete" if correct else "safe refusal" if safe_failure else "invalid itinerary")
        if args.expect_complete and not correct:
            return 1
        if not (correct or safe_failure):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
