# Real-provider itinerary and Trip Rescue replay

Run `python scripts/test_e2e_trip_flow.py` from the repository root. The script
loads the same `TripDraft` used by WhatsApp, builds a planner request, calls the
deployed tourism, hotel, transport, flight and route services, calls Bedrock,
formats the WhatsApp response, then sends a natural-language disruption to the
Trip Rescue extractor and recovery service. It does not send a real Meta message
or write a saved trip to Firestore.

Use `--base https://dreamdestiny.duckdns.org` to select the deployed gateway,
`--scenario flight_delay` to replay one case, and `--output PATH` to keep a
separate trace. The default trace and results are written to
`.e2e-trip-runs/trace.jsonl` and `.e2e-trip-runs/results.json`. The trace includes
the WhatsApp-shaped input, parsed trip, model prompts, Bedrock text and parsed
JSON, provider calls/results, itinerary, rescue response, and elapsed times.
It can contain trip details and should stay private. The directory is Git-ignored.

The replay calls Google Places New for regular opening hours and Google Routes
for driving gaps. It checks day count, transport source IDs, dated hotel source
ID and nightly target, unique sourced attractions, requested pace/interests,
arrival-before-sightseeing, opening hours, travel gaps, WhatsApp chunk size,
hotel transfer instructions, and basic Trip Rescue routing. A response is marked
`PASS` only for the checks that ran; it is not a booking or availability guarantee.

Planner timing now uses the provider's published weekly opening hours and routed
drive times. When hours or routes cannot be verified, the itinerary says so.
For arrival-day sightseeing, the planner reserves 90 minutes after a train/bus
arrival or 120 minutes after a flight arrival for transfer and check-in. These
are conservative allowances, not live station or airport queue estimates.
Interest-specific museum results are fetched from Google Places when requested;
only records in the destination city are used.

The real-provider replay does not prove that the live Meta WhatsApp webhook,
Redis session persistence, or Firestore write path is working. Use the webhook
integration tests and then a Meta test-number chat for those paths. Google Places
regular hours may differ on holidays. SerpApi hotel prices and transport seats
can change or disappear before booking; no supplier booking is performed.
