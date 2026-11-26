# Trip Rescue implementation and local testing

## Natural-language rescue details

For Bedrock Converse interpretation, set `BEDROCK_CONVERSE_MODEL_ID` to a model enabled for **Converse** in `BEDROCK_REGION`, alongside the existing `BEDROCK_API_KEY`. The API key must have access to the Bedrock Runtime Converse endpoint. The existing Gemma 4 31B planner model uses Bedrock's OpenAI-compatible endpoint and does not support Converse. Do not set the Converse model ID to `google.gemma-4-31b`. When Converse is not configured or unavailable, rescue interpretation uses the existing Bedrock Chat Completions model at temperature 0.1; if that also fails, the bot presents guided choices.

In both Trip Rescue modes, the bot sends the saved trip's dates and transport legs, the current message, the last ten rescue turns, a compact summary of older turns, and previously extracted fields to the rescue extraction endpoint. The Redis session persists these fields per WhatsApp number. The model returns strict JSON at temperature 0.1. Invalid JSON is retried once; if interpretation remains unavailable, the bot offers a four-choice WhatsApp list. After two unknown interpretations, it shows the same list instead of repeating the question. The bot also prevents sending the same reply twice consecutively.

For a missed return bus, the bot can ask one specific question (for example, current location), then recognizes a later explanation such as traffic using the earlier turn. It searches the **return** leg. A second model call words up to three provider-backed alternatives for WhatsApp; it includes only prices and times present in the provider results. If wording fails validation, the existing sourced option list is sent. Selecting an option and applying the suggested itinerary update still follow the existing approval flow when contextual mode is off. Supplier tickets are not changed.

Manual WhatsApp check with a saved active Hyderabad trip: send `Trip Rescue` → `i left the return bus` → expect one question such as `Where are you now?` → send `i left my return bus due to traffic` → expect return-leg alternatives or a clear provider-unavailable message, never the first question repeated. Send `Trip Rescue` again and `train is cancelled` to check train interpretation. For the loop guard, send `gibberish` twice; the second response should be a list with Missed transport, Delay, Cancellation, and Change plan. If the selected trip is over, Trip Rescue reports that separately and does not suggest expired travel.

Trip Rescue is an opt-in extension to the existing WhatsApp trip planner. It is **off by default** (`TRIP_RESCUE_ENABLED=false`). The original `POST /plan`, onboarding, PDF, and review flows are unchanged when the flag is off.

## Contextual auto-recovery (separate opt-in)

Set both `TRIP_RESCUE_ENABLED=true` and `TRIP_RESCUE_CONTEXTUAL_ENABLED=true` to use the contextual journey. The original choice-and-approval journey remains available when the contextual flag is false.

1. `Trip Rescue` lists up to three of the traveler's saved trips. Selecting one confirms the trip before any disruption is processed.
2. The traveler describes what happened in free text. Bedrock receives a compact view of the selected trip: dates, current transport and stay, a few itinerary activities, and reported commitments. Its first structured response classifies the issue and requests only the relevant tools. An already-arrived delay is forced to nearby discovery even if the model misclassifies it.
3. Read-only provider agents query only the needed domains: bus/train/flight, fresh SerpApi hotels, fresh Google Places attractions, or nearby Places plus Routes. Location-dependent incidents ask for a WhatsApp pin or precise landmark. The second Bedrock response must choose an ID from those actual results and can name one existing activity to replace. The supervisor rejects invented IDs and unsupported claims; no provider result means no itinerary change.
4. The bot sends one grounded recommendation and automatically versions the **suggested itinerary** using the existing Firestore transaction, after the trip was confirmed. The update never purchases, cancels, refunds, or changes a supplier booking. A reported booked activity is preserved. An unchanged or stale trip cannot be overwritten.

The two model requests carry bounded JSON rather than the full itinerary or raw provider payloads. The normal planner route and original Trip Rescue flow are unchanged by default. Provider results are search data; hotel room availability, refund rules, and attraction opening hours must still be confirmed with the supplier. This mode is reactive to a traveler message; continuous background monitoring is not implemented.

For a local test with provider/model mocks, run the planner and WhatsApp bot test commands below. For a live WhatsApp test after enabling the flags: send `Trip Rescue`, tap the intended saved trip, describe a disruption such as `My hotel room is dirty`, and check that the bot sends one sourced suggestion and a new itinerary version without an extra approval button. For `The bus was late and I reached Hyderabad`, share a current location pin when asked. Confirm that no outbound ticket appears.

## Current scope

1. A traveler plans a trip as before. The bot persists the generated itinerary. Generated items are recommendations, not bookings.
2. The traveler can add a reported commitment with `Booking add: transport | Train 123 | 2026-12-01T09:00+05:30 | 2026-12-01T15:00+05:30 | 1200`. Valid types are `transport`, `stay`, `activity`, and `other`. Times require timezone offsets. This is a *traveler-reported* booking; no supplier confirmation is performed.
3. The traveler sends `Trip Rescue`, then describes a delay, cancellation, closure, or preference change. The bot loads the durable trip and current itinerary from Firestore.
4. The planner builds a fresh provider context. A mobility agent and an experience agent independently call their read-only tool boundaries and each selects provider IDs using the configured model. The supervisor combines and filters the results. A model cannot create an option ID, price, time, or booking status.
5. The bot sends up to three options, asks the traveler to choose one, then requires a separate `Apply update` approval. It rechecks the chosen option before applying an itinerary-only revision. The Firestore transaction advances the trip version and stores the new itinerary version atomically. Repeated approval of the same run is idempotent; a stale version or a different option is rejected.
6. The bot explicitly states that the revision does **not** purchase, cancel, or modify a supplier booking. Automated monitoring, ticketing, payments, and refunds are not implemented.

### Already arrived late: nearby recovery

If a traveler says they **arrived/reached the destination late**, Trip Rescue no longer searches for another outbound bus, train, or flight. It asks for a current WhatsApp location pin or a precise landmark. The planner validates that the location is near the trip destination, searches fresh Google Places (New) results for nearby hotels and tourist attractions, and uses a Google Routes matrix to rank candidates by driving time. The nearest reachable hotel is always included. A lodging agent and a local experience agent independently select grounded candidates; their outputs can reference only Google place IDs from these searches.

The bot displays hotel recommendations with travel time and nearby sightseeing. Places does **not** prove room availability or price, and opening hours and ticket availability are not confirmed. After the traveler chooses and approves an option, the bot re-queries the sources, revises the suggested hotel and one upcoming sightseeing day, and preserves reported booked activities and supplier commitments. If no nearby route or place can be verified, the itinerary stays unchanged. The planner needs `GOOGLE_MAPS_API_KEY` with Places API (New), Geocoding API, and Routes API enabled.

The recovery result includes agent traces, provider provenance, retrieval time, and short expiry. Attraction alternatives carry a warning because opening hours and entry fees have not been verified. The selected option is stored in `recovery_history` on the new itinerary version. A selected transport recommendation replaces the corresponding outbound or return recommendation; an activity replacement updates an exact matching activity name. Unrelated itinerary content is retained.

## Components

| Component | Location | Responsibility |
|---|---|---|
| WhatsApp controller | `whatsapp-bot-service/app/services/trip_rescue.py` | Dedicated state path, choices, approval, messaging |
| Durable storage | `whatsapp-bot-service/app/storage/firestore_store.py` | Trips, commitments, recovery runs, atomic version update |
| Incoming queue | `whatsapp-bot-service/app/services/event_worker.py` | Redis stream consumer, retry, dead-letter after five attempts |
| Gateway | `whatsapp-bot-service/app/clients/planner_gateway.py` | Calls the planner recovery endpoint |
| Supervisor | `planner-service/app/recovery/service.py` | Classifies change, identifies affected commitments, delegates and validates |
| Specialist agents | `planner-service/app/recovery/agents.py` | Independent mobility and experience selection using typed tools |
| API | `planner-service/app/api/routes/recovery.py` | `POST /v1/recovery` |

The recovery endpoint is intended for the internal bot-to-planner network. It has no user authentication of its own. Do not expose planner port 8000 publicly in production. The current Compose development file publishes it for local testing.

## Test locally without a Meta account

Use Python 3.11 or newer and install each service's requirements. On Windows PowerShell, from the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'planner-service'
python -m pytest planner-service/tests -q -p asyncio -p no:cacheprovider
$env:PYTHONPATH = 'whatsapp-bot-service'
python -m pytest whatsapp-bot-service/tests -q -p asyncio -p no:cacheprovider
```

The webhook integration tests send Meta-shaped POST payloads to the FastAPI webhook through ASGI. They cover both `Trip Rescue` → disruption → option button → approval and the contextual `Trip Rescue` → trip confirmation → disruption → automatic itinerary version. WhatsApp sending, provider lookup, and model output are mocked. The agent tests reject invented IDs and verify that an already-arrived traveler does not receive an outbound transport option. These tests do not prove that third-party inventory is available or that a live Meta account is configured.

## Test actual WhatsApp messages without deploying

1. Create or open a Meta developer app with WhatsApp Cloud API. In its WhatsApp API setup, use the test business number, add your personal WhatsApp number as an allowed test recipient, and obtain the **phone number ID** and a valid access token. Configure webhook `messages` delivery in the app. See [Meta's WhatsApp Business Platform guide](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview/).
2. Put credentials in an untracked `.env`: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN` (choose a new random string), `WHATSAPP_APP_SECRET`, `BEDROCK_API_KEY`, `GOOGLE_MAPS_API_KEY`, `SERPAPI_API_KEY`, and `TRIP_RESCUE_ENABLED=true`. Configure Firestore credentials for persistent trips. Never paste tokens in chat or commit them.
3. Start the local services with `docker compose up --build`. Check `http://localhost:8007/health` and `http://localhost:8000/health`. Check `http://localhost:8007/ready`; for a durable trial it should report Redis and Firestore configured. In development mode, absent Firestore credentials cause an in-memory fallback, which loses trips on restart.
4. Run `cloudflared tunnel --url http://localhost:8007` in another terminal. It returns a temporary HTTPS URL. Cloudflare documents quick tunnels for local testing; anyone with that URL can reach the local service, so keep HMAC verification enabled. See [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
5. In Meta's webhook settings, set callback URL to `https://<temporary-host>/webhook` and verification token to your `WHATSAPP_VERIFY_TOKEN`. Subscribe to the `messages` field. Meta will call the GET verification route, then POST signed messages to the same URL. The bot validates the `X-Hub-Signature-256` header when `WHATSAPP_APP_SECRET` is set.
6. From your allowed personal WhatsApp number, message the Meta test number. First complete the existing `New trip` planner flow. Then send `Trip Rescue`, report a disruption (for example, `My outbound train is delayed by 2 hours`), choose an option, and tap `Apply update`. To test a reported commitment, send the `Booking add:` command above before starting Trip Rescue.
   For an arrival test, send `Trip Rescue` → `The bus was late and I reached Hyderabad by 9 am` → share a WhatsApp location pin near Hyderabad or type a precise landmark such as `MGBS bus station` → choose a nearby stay → `Apply update`. Expect hotel and sightseeing suggestions, with no replacement outbound transport.
7. Confirm the resulting message says **itinerary updated, supplier booking unchanged**. Check the bot and planner logs for the recovery run, agent traces, and errors. Test a cancellation and an unrecognized change. Restarting the tunnel gives a new URL, so update Meta's callback.

For the contextual mode, also set `TRIP_RESCUE_CONTEXTUAL_ENABLED=true` in `.env` before starting Compose. The sequence is `Trip Rescue` → select the saved trip → describe what happened → share a location pin if asked → receive one recommendation and a new itinerary version automatically. No option or `Apply update` button appears in this mode. For an arrival delay, the reply names the nearby stay and up to two nearby sights. Inspect the newly saved itinerary to verify that reported booked activities remain intact.

The Meta test number and temporary tunnel exercise real inbound and outbound WhatsApp delivery but do not require deploying the app. Provider/API credentials are still required for live travel results. The bot must run with `APP_ENV=development` or `production` for real outbound messages; `APP_ENV=test` intentionally mocks sending. The initial test number may restrict recipient accounts according to Meta's current setup UI.

## Operational boundaries

- `TRIP_RESCUE_ENABLED=true` in production requires Redis, Firestore, WhatsApp credentials, and the Meta app secret. Startup fails if they are missing.
- Each recovery request creates a fresh orchestrator to bypass the ordinary planner cache. Provider APIs may still have their own caches or lag; search results are never represented as guaranteed inventory.
- With Trip Rescue enabled and Redis connected, the webhook writes each incoming event to a Redis stream before acknowledging Meta. A worker acknowledges the stream entry only after processing; failures are retried and exhausted entries move to a dead-letter stream. Development without Redis and the disabled feature flag retain the legacy FastAPI background path. Redis persistence (AOF) is configured in Compose, but outbound delivery remains at-least-once after a crash; a transactional outbound outbox is still needed before a high-volume production launch.
- The current dependency check covers explicit reported commitments and basic delay propagation. It does not yet verify venue hours, cross-city transfers, refund rules, detailed accessibility, or booking provider terms. These must be addressed before claiming fully autonomous travel recovery.
- No proactive monitoring or paid supplier transaction is enabled. Those require contracted data access, consent, message templates, reconciliation, and support processes.
