# Travel Planner WhatsApp Bot — Production Implementation Plan

## Objective

Implement a production-ready WhatsApp conversational interface for the existing Travel Planner backend.

The existing travel-planner microservices and gateway are already deployed on EC2 behind Nginx. **Do not rewrite or unnecessarily modify the existing travel-planner services.**

The new WhatsApp layer must:

- Receive WhatsApp messages through Meta WhatsApp Cloud API webhooks.
- Support multiple users concurrently.
- Maintain isolated conversation state per WhatsApp user.
- Support interactive selections and free-form text.
- Convert conversational input into the existing `TripRequest`.
- Reuse the existing backend gateway and travel-planning pipeline.
- Use Redis for fast, short-lived active conversation state.
- Use Firestore for durable users, conversations, trips and itineraries.
- Recover useful history after Redis expiration or service restart.
- Handle duplicate webhook deliveries safely.
- Handle retries, timeouts and external failures safely.
- Never mix one user's conversation with another user's.
- Keep the WhatsApp layer independent from tourism, transport, hotel and planning services.

---

## 1. Target Architecture

```text
                         WhatsApp User
                              |
                              v
                    Meta WhatsApp Cloud API
                              |
                         Webhook
                              |
                              v
                           Nginx
                              |
                              v
                  +-------------------------+
                  |   WhatsApp Bot Service  |
                  |                         |
                  | Webhook API             |
                  | Message Handler         |
                  | Conversation Manager    |
                  | State Machine            |
                  | Message Understanding   |
                  | WhatsApp Client         |
                  +-----------+-------------+
                              |
                 +------------+-------------+
                 |                          |
                 v                          v
              Redis                     Firestore
        Active session state       Persistent history
        TTL / idempotency          Users / messages
        locks / queue state        trips / itineraries
                 |
                 v
          Conversation Engine
                 |
                 v
          Existing Backend Gateway
                 |
        +--------+---------+---------+
        |                  |         |
        v                  v         v
    Tourism            Transport   Hotels
        |                  |         |
        +------------------+---------+
                           |
                           v
                      Trip Planner
                           |
                           v
                       Validator
                           |
                           v
                       Itinerary
                           |
                           v
                    WhatsApp Client
                           |
                           v
                      WhatsApp User
```

The existing travel-planner backend remains the source of travel data and itinerary generation.

---

## 2. Important Architectural Rule

**Do not maintain a permanent connection per WhatsApp user.**

WhatsApp is event-driven.

Each incoming message is an HTTP webhook event containing the sender identity.

Process messages as:

```text
User A -> webhook -> process -> response
User B -> webhook -> process -> response
User C -> webhook -> process -> response
```

Use the WhatsApp sender ID (`wa_id` / `from`) as the user/conversation key.

The application process itself must be stateless between requests. Shared state belongs in Redis/Firestore.

This is required for horizontal scaling.

---

## 3. New Service

Create a separate service:

```text
whatsapp-bot-service/
```

Suggested structure:

```text
whatsapp-bot-service/
├── app/
│   ├── main.py
│   ├── api/
│   │   └── webhook.py
│   ├── handlers/
│   │   ├── message_handler.py
│   │   ├── interactive_handler.py
│   │   └── status_handler.py
│   ├── conversation/
│   │   ├── manager.py
│   │   ├── state_machine.py
│   │   ├── session.py
│   │   └── prompts.py
│   ├── understanding/
│   │   ├── message_parser.py
│   │   └── schemas.py
│   ├── storage/
│   │   ├── redis_store.py
│   │   ├── firestore_store.py
│   │   └── idempotency.py
│   ├── whatsapp/
│   │   ├── client.py
│   │   ├── messages.py
│   │   └── templates.py
│   ├── clients/
│   │   └── planner_gateway.py
│   ├── schemas/
│   │   ├── webhook.py
│   │   ├── conversation.py
│   │   ├── trip.py
│   │   └── response.py
│   ├── services/
│   │   ├── trip_service.py
│   │   └── memory_service.py
│   └── config.py
├── tests/
├── requirements.txt
├── .env.example
├── Dockerfile
└── README.md
```

Keep modules loosely coupled and dependency-injectable.

---

## 4. Conversation State Machine

Implement a deterministic state machine:

```text
START
COLLECT_ORIGIN
COLLECT_DESTINATION
COLLECT_DATES
COLLECT_TRAVELERS
COLLECT_BUDGET
COLLECT_TRANSPORT
COLLECT_HOTEL
COLLECT_INTERESTS
CONFIRM_TRIP
GENERATING
COMPLETED
MODIFYING
ERROR
```

Typical flow:

```text
START
  -> COLLECT_ORIGIN
  -> COLLECT_DESTINATION
  -> COLLECT_DATES
  -> COLLECT_TRAVELERS
  -> COLLECT_BUDGET
  -> COLLECT_TRANSPORT
  -> COLLECT_HOTEL
  -> COLLECT_INTERESTS
  -> CONFIRM_TRIP
  -> GENERATING
  -> COMPLETED
```

The state machine must support multiple fields supplied in one message.

Example:

> I want to travel from Chennai to Goa on October 15 for 4 days with 2 people and a budget of 20k.

The system should extract all known fields and skip questions already answered.

The LLM must not directly control the state machine.

---

## 5. TripRequest

Use the existing backend `TripRequest` schema if available.

Do not create a conflicting WhatsApp-only trip schema.

Example:

```json
{
  "origin": "Chennai",
  "destination": "Goa",
  "start_date": "2026-10-15",
  "end_date": "2026-10-19",
  "travelers": 2,
  "preferences": {
    "budget": {
      "level": "medium",
      "maximum": 20000
    },
    "transport": {
      "preference": "cost_effective"
    },
    "hotel": {
      "class": "3_star"
    },
    "activities": {
      "interests": ["beaches", "history"]
    }
  }
}
```

Use the actual deployed schema rather than duplicating business rules.

---

## 6. Message Understanding

Users may type arbitrary text.

Create a message-understanding layer:

```text
Raw WhatsApp message
        |
        v
Message Understanding
        |
        v
Structured extracted fields
        |
        v
Pydantic validation
        |
        v
Conversation State Machine
```

Example:

```text
"Actually make it 4 days and keep the budget below 20k."
```

becomes:

```json
{
  "duration_days": 4,
  "budget_maximum": 20000
}
```

Rules:

- Use deterministic parsing first for simple inputs.
- Use an LLM only when natural-language interpretation is needed.
- Require structured output.
- Validate all extracted values.
- Reject unsafe/invalid extraction.
- Never let the LLM invent travel data.
- Never let the LLM call travel services.
- Never let the LLM directly change conversation state.

---

## 7. Redis — Active Conversation State

Use Redis for active sessions.

Key:

```text
travel:conversation:{wa_id}
```

Example:

```json
{
  "conversation_id": "conv_123",
  "wa_id": "919876543210",
  "state": "COLLECT_TRANSPORT",
  "trip_request": {
    "origin": "Chennai",
    "destination": "Goa",
    "start_date": "2026-10-15",
    "end_date": "2026-10-19",
    "travelers": 2
  },
  "last_message_id": "wamid.xxx",
  "last_activity": "2026-09-28T10:20:00Z",
  "version": 7
}
```

Use a configurable TTL, for example:

```text
CONVERSATION_TTL_SECONDS=172800
```

Default: 48 hours.

Refresh TTL on valid user activity.

Do not store the complete message history in Redis.

Recommended key namespaces:

```text
travel:conversation:{wa_id}
travel:lock:{wa_id}
travel:idempotency:{message_id}
travel:queue:{job_id}
```

---

## 8. Firestore — Durable Storage

Use Firestore for permanent data.

Recommended structure:

```text
users/{wa_id}

users/{wa_id}/conversations/{conversation_id}

users/{wa_id}/conversations/{conversation_id}/messages/{message_id}

users/{wa_id}/trips/{trip_id}

users/{wa_id}/trips/{trip_id}/itineraries/{version_id}
```

### User

```json
{
  "wa_id": "919876543210",
  "display_name": "...",
  "created_at": "...",
  "updated_at": "...",
  "last_seen_at": "..."
}
```

### Conversation

```json
{
  "status": "completed",
  "started_at": "...",
  "updated_at": "...",
  "completed_at": "...",
  "current_state": "COMPLETED"
}
```

### Message

Store:

- message_id
- direction
- message_type
- text when applicable
- timestamp
- processing status
- minimal required metadata

Do not store unnecessary secrets or access tokens.

### Trip

Store:

- TripRequest
- itinerary
- destination
- dates
- travelers
- status
- created_at
- updated_at

---

## 9. Redis + Firestore Responsibilities

### Redis

Short-term:

- current conversation state
- current TripRequest
- current state-machine state
- short-lived locks
- idempotency
- temporary queue/job information

### Firestore

Long-term:

- users
- conversation history
- messages
- completed trips
- itineraries
- itinerary versions
- durable preferences

Redis is not permanent memory.

Firestore is not the replacement for fast active-session state.

---

## 10. Conversation Recovery

When a user sends a message:

```text
wa_id
  |
  v
Redis
  |
  +-- found -> continue current conversation
  |
  +-- miss -> query Firestore
                  |
                  +-- active/recent conversation
                  |
                  +-- previous trips
                  |
                  +-- user preferences
```

Example after two days:

> What hotel did you suggest for my Goa trip?

If Redis has expired:

```text
Redis miss
 -> Firestore
 -> recent Goa trip
 -> itinerary
 -> hotel
 -> response
```

If multiple matching trips exist, do not guess.

Example:

```text
I found multiple Goa trips. Which one do you mean?

[Oct 15–19]
[Nov 02–06]
```

---

## 11. WhatsApp Interactive Messages

Use:

- reply buttons for small fixed choices
- list messages for larger choice sets
- WhatsApp Flows for multi-field forms when useful
- normal text for free-form input

Example:

```text
What transport do you prefer?

[Train]
[Bus]
[Any]
```

Users must still be able to type natural-language responses.

---

## 12. Multi-User Isolation

Never use:

```python
current_user = ...
```

Never use a process-local dictionary as the source of truth.

Always route using the incoming user's `wa_id`.

Every outgoing message must explicitly specify:

```python
send_message(
    recipient=wa_id,
    message=...
)
```

Test concurrent users:

```text
User A
User B
User C
```

and verify zero cross-user state contamination.

---

## 13. Same-User Concurrency

Two messages from the same user can arrive close together.

Use a short-lived Redis lock:

```text
travel:lock:{wa_id}
```

Flow:

```text
Acquire lock
    |
Load latest state
    |
Process message
    |
Persist state
    |
Release lock
```

Use a short lock TTL and ensure locks cannot remain indefinitely.

---

## 14. Idempotency

WhatsApp webhook events must be treated as retryable.

Use the WhatsApp message ID:

```text
travel:idempotency:{message_id}
```

Before processing:

```text
already processed?
    -> ignore safely
```

Otherwise process exactly once from the application's perspective.

Persist appropriate processing state in Firestore so crashes/retries can recover safely.

---

## 15. Webhook API

Implement:

```text
GET /webhooks/whatsapp
POST /webhooks/whatsapp
```

GET:

- Meta webhook verification
- verify token validation

POST:

- parse webhook payload
- normalize incoming events
- handle text
- handle buttons/lists
- handle status events
- ignore unsupported events safely
- acknowledge quickly

Do not block webhook acknowledgement on expensive itinerary generation.

---

## 16. Background Processing

Use an internal queue abstraction.

Preferred flow:

```text
WhatsApp webhook
      |
      v
validate event
      |
      v
persist/enqueue
      |
      v
return HTTP 200 quickly
      |
      v
worker
      |
      v
conversation processing
      |
      v
planner gateway
      |
      v
WhatsApp response
```

Initially the queue can use Redis.

Keep a queue interface so it can later be replaced with AWS SQS or RabbitMQ without rewriting conversation logic.

---

## 17. Existing Planner Integration

Create:

```text
PlannerGatewayClient
```

The WhatsApp service calls only the existing backend gateway.

Do NOT call these directly:

```text
Tourism Service
Transport Service
Hotel Service
Route Service
```

The WhatsApp layer should use:

```text
TripRequest
   -> Existing Backend Gateway
   -> Existing Planner
   -> Itinerary
```

Use:

- connection pooling
- explicit timeouts
- limited safe retries
- structured errors
- correlation IDs

---

## 18. Request Correlation

Create a correlation ID for each incoming message.

Propagate it through:

```text
WhatsApp Bot
    -> Backend Gateway
    -> Travel Services
```

Structured logs must include it.

This must allow one user request to be traced across services.

---

## 19. Error Handling

### Invalid user input

Explain the problem and ask for correction.

### Missing information

Ask the next required question.

### Planner unavailable

Do not fabricate an itinerary.

### External provider failure

Use existing backend fallback behavior.

### WhatsApp API failure

Retry safely where appropriate and persist failed outbound work when required.

Never expose stack traces or internal errors to users.

---

## 20. WhatsApp Messaging Window

The application may retain conversation/trip history in Firestore according to its data-retention policy.

WhatsApp messaging rules are separate.

If the user sends a message after several days, the bot can retrieve their stored history and answer.

If the business proactively initiates a message outside the permitted customer-service window, use the appropriate approved WhatsApp template mechanism.

Do not bypass WhatsApp platform rules.

---

## 21. Durable User Preferences

Keep durable preferences separate from temporary trip state.

Example:

```json
{
  "preferences": {
    "preferred_transport": "train",
    "hotel_class": "3_star"
  }
}
```

Do not automatically convert every conversation statement into permanent memory.

Trip-specific information belongs to the trip.

---

## 22. Modification Flow

After an itinerary is generated, support messages such as:

```text
Make the hotel cheaper.
```

```text
Change the dates.
```

```text
Use train instead.
```

```text
Add more beaches.
```

Flow:

```text
Existing trip
    |
requested modification
    |
updated TripRequest/context
    |
existing planner
    |
validator
    |
new itinerary version
    |
WhatsApp response
```

Do not start an unrelated conversation.

---

## 23. Itinerary Versioning

Do not overwrite the only itinerary.

Store:

```text
users/{wa_id}/trips/{trip_id}/itineraries/{version_id}
```

Each modification creates a new version.

Track:

```json
{
  "version": 2,
  "is_current": true,
  "created_at": "..."
}
```

---

## 24. Security

Implement:

- HTTPS through Nginx
- webhook verification
- environment-based secrets
- Firebase Admin SDK securely
- Redis authentication/TLS where applicable
- no secrets in source control
- no secrets in logs
- input validation
- payload limits
- rate limiting
- request timeouts
- least-privilege credentials

Never expose Redis, Firestore credentials or WhatsApp access tokens to users.

---

## 25. Environment Configuration

Create `.env.example`:

```env
APP_ENV=production

WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_API_VERSION=

REDIS_URL=
REDIS_PASSWORD=

FIREBASE_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=

PLANNER_GATEWAY_URL=

CONVERSATION_TTL_SECONDS=172800
REQUEST_TIMEOUT_SECONDS=30

LOG_LEVEL=INFO
```

Never hard-code credentials.

---

## 26. Logging

Use structured JSON logs.

Example:

```json
{
  "timestamp": "...",
  "level": "INFO",
  "service": "whatsapp-bot",
  "correlation_id": "...",
  "wa_id_hash": "...",
  "conversation_id": "...",
  "event": "message_processed",
  "state": "COLLECT_DATES",
  "duration_ms": 182
}
```

Avoid unnecessary logging of:

- phone numbers
- message contents
- access tokens
- API keys
- credentials

Hash/anonymize identifiers where practical.

---

## 27. Health and Readiness

Implement:

```text
GET /health
GET /ready
```

`/health`:

- process is alive

`/ready`:

- Redis available
- Firestore available
- required configuration loaded

Do not make expensive travel API calls from health endpoints.

---

## 28. Metrics

Track:

```text
webhook_received_total
webhook_processing_errors_total
messages_processed_total
duplicate_messages_total
conversation_completed_total
conversation_expired_total
planner_requests_total
planner_failures_total
planner_latency
whatsapp_send_success_total
whatsapp_send_failure_total
redis_errors_total
firestore_errors_total
message_processing_latency
```

Keep metrics implementation modular.

---

## 29. Firestore Rules

Avoid unbounded documents.

Do not store an entire conversation in one document.

Use message subcollections.

Use server timestamps.

Required query patterns:

1. user by WhatsApp ID
2. recent/active conversation
3. recent trips
4. trip by destination/date when needed
5. itinerary retrieval
6. conversation message retrieval

Create indexes only when required.

---

## 30. Deployment

Deploy the WhatsApp service on the existing EC2 environment.

Do not expose it directly if Nginx can proxy it.

Example public route:

```text
https://api.example.com/whatsapp/webhook
```

Nginx:

```text
/whatsapp/
    -> whatsapp-bot-service
```

Do not break existing gateway routes.

Run the service under systemd or Docker Compose with automatic restart.

---

## 31. Scaling

Initial deployment:

```text
1 EC2
Nginx
Backend Gateway
WhatsApp Bot
Redis
Existing Services
```

Future:

```text
                 Load Balancer
                      |
             +--------+--------+
             |                 |
        Bot Instance 1    Bot Instance 2
             |                 |
             +--------+--------+
                      |
                    Redis
                      |
                  Firestore
```

The WhatsApp application must therefore remain stateless at process level.

---

## 32. Testing

Implement tests for:

### Webhook

- valid verification
- invalid verification
- text message
- button message
- list message
- unsupported message
- malformed payload

### Conversation

- state transitions
- missing fields
- multiple fields in one message
- modification
- resume
- timeout

### Redis

- save/load
- TTL
- expiration
- locking
- idempotency

### Firestore

- user creation
- conversation persistence
- message persistence
- trip persistence
- itinerary persistence
- trip retrieval
- multiple-trip selection

### Planner

- correct TripRequest
- success
- timeout
- failure

### Multi-user

Run concurrent User A/B/C scenarios and verify complete isolation.

---

## 33. Load Testing

Before production launch, test at least:

```text
10 concurrent users
50 concurrent users
100 concurrent users
```

Measure:

- webhook latency
- Redis latency
- Firestore latency
- message processing latency
- planner latency
- WhatsApp API latency
- error rate
- CPU
- memory

---

## 34. Implementation Order

### Phase 1 — Foundation

Create:

- FastAPI service
- configuration
- dependency management
- structured logging
- health endpoints
- deployment setup

### Phase 2 — Webhook

Implement:

- GET verification
- POST webhook
- payload normalization

### Phase 3 — WhatsApp Client

Implement:

- text
- buttons
- lists
- templates
- error handling

### Phase 4 — Redis

Implement:

- session model
- save/load
- TTL
- per-user lock
- idempotency

### Phase 5 — Firestore

Implement:

- users
- conversations
- messages
- trips
- itinerary versions

### Phase 6 — State Machine

Implement all conversation states and transitions.

### Phase 7 — Message Understanding

Implement deterministic extraction first, then structured LLM extraction where required.

### Phase 8 — Planner Integration

Connect the normalized TripRequest to the existing backend gateway.

### Phase 9 — History and Resume

Implement Redis miss -> Firestore recovery and previous-trip lookup.

### Phase 10 — Modification

Implement itinerary modifications and versioning.

### Phase 11 — Reliability

Implement:

- queue
- retries
- timeouts
- idempotency
- locks
- recovery

### Phase 12 — Production Hardening

Implement:

- security
- rate limiting
- metrics
- monitoring
- load tests
- deployment documentation

---

## 35. Definition of Done

The implementation is complete only when:

- WhatsApp webhook receives messages.
- Webhook verification works.
- Multiple users can chat concurrently.
- User conversations never mix.
- Text input works.
- Buttons/lists work.
- Free-form messages work.
- Multiple fields can be extracted from one message.
- Conversation state survives process restart.
- Redis TTL works.
- Firestore persistence works.
- Redis expiration can recover useful context from Firestore.
- Previous trips can be retrieved.
- Follow-up questions about previous trips work.
- Existing planner gateway is reused.
- Travel-service logic is not duplicated.
- Itineraries are persisted.
- Itinerary modifications work.
- Itinerary versions are stored.
- Duplicate webhooks are safely handled.
- Same-user race conditions are handled.
- Planner/provider failures never produce fabricated responses.
- Secrets are protected.
- Health/readiness endpoints work.
- Structured logs contain correlation IDs.
- Metrics are available.
- Existing travel-planner behavior remains unchanged.
- Tests pass.
- Concurrent-user tests pass.
- The service survives EC2/service restart.

---

## 36. Critical Rules for the Implementation Agent

1. Do not rewrite existing travel services.
2. Do not move travel business logic into the WhatsApp layer.
3. Do not create permanent connections per user.
4. Do not use Python process memory as the source of truth for sessions.
5. Do not use Redis as permanent storage.
6. Do not use Firestore as the replacement for Redis active state.
7. Do not send every message blindly to an LLM.
8. Do not allow the LLM to control the conversation state machine.
9. Do not allow the LLM to invent travel facts.
10. Do not call individual travel services directly from WhatsApp.
11. Use the existing backend gateway.
12. Never mix user state.
13. Make webhook processing idempotent.
14. Handle same-user concurrent messages safely.
15. Never fabricate an itinerary when backend planning fails.
16. Keep WhatsApp-specific logic isolated.
17. Use environment variables for secrets.
18. Keep the service horizontally scalable.
19. Preserve existing backend compatibility.
20. Implement and test phase-by-phase.
21. Inspect the existing backend schemas and routes before creating duplicate schemas.
22. Reuse existing authentication/configuration conventions where safe.
23. Do not make unrelated changes to the deployed travel planner.
24. Document every new environment variable and deployment step.
25. Do not mark a phase complete until its tests pass.

---

## 37. Final User Experience

Normal flow:

```text
User
 |
 | "Plan me a trip to Goa"
 v
WhatsApp
 |
 v
Conversation Engine
 |
 | asks structured questions
 | accepts natural language
 v
TripRequest
 |
 v
Existing Backend Gateway
 |
 +--> Tourism
 +--> Transport
 +--> Hotels
 +--> Routes
 |
 v
Planning Agent
 |
 v
Validator
 |
 v
Itinerary
 |
 v
Firestore
 |
 v
WhatsApp
 |
 v
User
```

Returning-user flow:

```text
User
 |
 | "What hotel did you suggest?"
 v
WhatsApp
 |
 v
wa_id
 |
 v
Redis
 |
 | miss
 v
Firestore
 |
 v
Previous Trip
 |
 v
Itinerary
 |
 v
Answer
```

The travel-planner core must remain independent of the presentation channel. A future website, mobile application, Telegram bot or other client should be able to consume the same backend without rewriting the core travel-planning system.
