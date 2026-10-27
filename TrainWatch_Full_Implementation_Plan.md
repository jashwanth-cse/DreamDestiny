# TrainWatch --- Full Implementation Plan

**Revision:** 23 October 2026\
**Purpose:** Agent-ready end-to-end plan to implement, validate, and
prepare TrainWatch for production\
**Status:** Phases 0--3 are already completed. Preserve them; continue
from the next incomplete phase.

------------------------------------------------------------------------

## 1. Project objective and scope

Build **TrainWatch**, a mobile app that helps users monitor Indian
train-seat availability and receive alerts when a chosen condition
becomes true. It is **not** a ticket-booking app.

The finished product must allow a user to: 1. Sign in securely with
Google. 2. Search trains using source station, destination station, Date
of Journey (DOJ), travel class, and quota. 3. Get station suggestions
while typing. 4. View matching train results in a polished, accessible
interface. 5. Tap a class to see the exact availability returned by the
existing train API. 6. Create, list, pause, resume, and delete
seat-availability reminders. 7. Receive push notifications when a
configured condition is met. 8. Manage devices, notification
permissions, and reminders. 9. Recover gracefully from network failures,
expired sessions, partial responses, and upstream outages.

The target UI is based on the user-provided reference: clean search page
with From/To fields and swap action, journey date picker, class and
quota selectors, and a prominent Search Trains button.

### Out of scope

-   Ticket booking, payments, passenger details, PNR creation, or ticket
    purchase.
-   Rewriting or redeploying the existing train service unless
    separately authorized.
-   Hardcoding credentials or production identifiers in source control.

## 2. Existing APIs and codebase

Base URL: `https://dream-destiny.cloud.run`

### Station search / autocomplete

`GET /api/v1/stations/search?q=rajapalayam`

Use this while the user types into either station field. Debounce
requests and display station name plus code/metadata actually returned
by the service.

### Train search

`GET /api/v1/trains/search?from=Rajapalayam&to=Chennai&date=24-07-2026&travelClass=3A&sortBy=fare`

Parameters: - `from`: selected source station name in the format
accepted by the existing endpoint. - `to`: selected destination station
name in the format accepted by the existing endpoint. - `date`:
`DD-MM-YYYY`. - `travelClass`: class code accepted by the existing
API. - `sortBy`: default `fare`, unless the verified API contract
indicates otherwise.

### Availability

`POST /api/v1/trains/availability`

The user has already verified this endpoint's request contract and
response schema. Reuse the verified contract and artifacts. Do not spend
another phase re-discovering or re-verifying it. Map UI class labels
(such as SL, 3A/3AC, 2A/2AC) to the exact API values established by that
contract.

### Existing train-service code

`E:\Projects\Dream Destiny v2.0\transport-service\train`

Read this codebase when necessary to understand actual response fields,
error behavior, validation, and supported class codes. Treat it as
read-only for this project unless the user separately authorizes
changes.

### Integration principles

-   Keep endpoint URLs and request mapping in a dedicated
    adapter/client, never scattered across UI components.
-   Use environment-specific configuration; do not assume local,
    staging, and production share credentials.
-   Parse external responses into stable internal DTOs and expose only
    fields the app needs.
-   Do not invent missing train, route, timing, fare, or availability
    values.
-   Include timeouts, structured errors, bounded retries for safe
    operations, and request IDs.
-   Mock upstream responses for automated tests. Live API integration
    testing happens only after the user supplies/approves credentials
    and explicitly approves the test.

------------------------------------------------------------------------

## 3. System architecture

### 3.1 Logical architecture

``` text
React Native mobile app
  ├── Google Sign-In (Firebase Authentication)
  ├── Search / Results / Availability / Reminder screens
  └── FCM device token registration
             │ HTTPS + Firebase ID token
             ▼
FastAPI backend (stateless)
  ├── Auth middleware/dependencies
  ├── Search/availability API proxy or adapter
  ├── Reminder application service
  ├── Domain rule evaluator
  ├── Repository interfaces
  └── Task/notification dispatch interfaces
       │             │               │
       ▼             ▼               ▼
 Existing Train API  Firestore      Cloud Tasks / Scheduler
 dream-destiny...    data store     asynchronous checks
                                      │
                                      ▼
                                Worker service
                                      │
                            Train API + rule evaluator
                                      │
                                      ▼
                                Notification outbox
                                      │
                                      ▼
                               Firebase Cloud Messaging
                                      │
                                      ▼
                               User's device
```

The existing train API is an external dependency to TrainWatch. Do not
refactor it as part of this project.

### 3.2 System-design principles

**Separation of concerns** - UI components render state and forward user
actions; they do not implement API or reminder business logic. - API
routes validate/authenticate and call application services. - Domain
functions implement reminder rules as pure, deterministic functions. -
Repository interfaces isolate Firestore from business logic. - External
APIs and FCM are behind adapters/interfaces.

**High cohesion, loose coupling** - Keep each module responsible for one
concept. - Depend on interfaces, not concrete storage/network
implementations. - Avoid circular imports and global mutable state.

**Stateless services and horizontal scaling** - Keep FastAPI request
handling stateless. Store durable state in Firestore and queued work in
managed task services. - Do not rely on process memory for sessions,
schedules, deduplication, or reminder ownership. - Make handlers safe
under concurrent requests and multiple worker instances.

**Asynchronous processing** - Search and availability requests are
request/response operations with strict timeouts. - Reminder checks and
notifications are asynchronous; enqueue work and return promptly. - Do
not run an unbounded polling loop inside a web server process.

**Idempotency and at-least-once delivery** - Assume tasks and
notification attempts may run more than once. - Use stable idempotency
keys and atomic Firestore transactions/conditional writes where
appropriate. - Persist notification intent before sending; track
pending/sent/failed states.

**Failure isolation** - Timeouts and circuit-breaker-like protection
should prevent an upstream outage from exhausting all app capacity. -
Retry only safe/transient failures, with bounded exponential backoff and
jitter. - Never treat upstream failure as "no seats available."

**Security by design** - Verify Firebase ID tokens server-side. -
Authorize every resource by authenticated UID. - Use least-privilege
service accounts and secret management. - Keep PII and tokens out of
logs. - Validate every input and rate-limit expensive endpoints.

**Observability** - Structured logs, request/correlation IDs,
latency/error metrics, queue age, reminder success rate, and
notification delivery outcomes. - Never log access tokens,
service-account private keys, FCM tokens, or full sensitive payloads.

**Cost and quota awareness** - Avoid per-user tight polling. Define
minimum intervals, quotas, retention, and maximum active reminders based
on upstream limits and estimated cloud cost. - Prefer scheduling only
due reminders; use a shared scheduler/dispatcher and bounded worker
concurrency rather than one always-running loop per reminder. - Add
budget alerts and document likely cost drivers before cloud resources
are created.

**Maintainability** - Type annotations, linting, formatting, tests,
migrations/index documentation, runbooks, and architecture decisions. -
No premature microservices split: begin with a modular monolith plus a
separate worker entrypoint/service if required. Split services only when
scaling or ownership demands it.

------------------------------------------------------------------------

## 4. Recommended technology choices

-   **Mobile:** React Native + TypeScript. Follow the existing app setup
    if one exists; do not replace frameworks without a documented
    reason.
-   **Authentication:** Firebase Authentication with Google Sign-In.
-   **Backend:** Python + FastAPI.
-   **Database:** Cloud Firestore in Native mode.
-   **Scheduling/queue:** Cloud Scheduler to trigger a dispatcher and
    Cloud Tasks to execute bounded per-reminder or batched work. Confirm
    suitability against quotas and expected volume before
    implementation.
-   **Push notifications:** Firebase Cloud Messaging.
-   **Hosting:** Cloud Run for stateless API and worker endpoints if
    that matches the existing environment.
-   **Secrets:** Google Secret Manager in deployed environments; local
    `.env` files ignored by Git.
-   **Testing:** pytest, API contract fixtures, React Native tests, type
    checks, linting, security/dependency scanning.
-   **CI:** Existing GitHub Actions/CI conventions. Keep main branch
    protections and required checks.

If the repository already has equivalent, working choices from completed
phases, preserve them unless a concrete incompatibility is found.

------------------------------------------------------------------------

## 5. Authentication and authorization

### Mobile authentication

1.  Configure Firebase project and Google provider using credentials
    supplied by the user through approved secure channels.
2.  Implement Google Sign-In through Firebase Authentication.
3.  Handle sign-in, cancellation, sign-out, expired sessions, and token
    refresh.
4.  Send the Firebase ID token as `Authorization: Bearer <token>` to the
    TrainWatch backend over HTTPS.
5.  Never send Google client secrets or service-account credentials in
    the mobile app.

### Backend authentication

1.  Use Firebase Admin SDK to verify the ID token on protected routes.
2.  Derive UID only from the verified token.
3.  Reject missing, invalid, expired, or revoked tokens with appropriate
    401 responses.
4.  Enforce resource ownership on every reminder/device endpoint; return
    403/404 safely without leaking another user's data.
5.  Separate public health/readiness endpoints from authenticated user
    APIs.
6.  Use a service account with minimal required permissions. Never embed
    its private key in source control or mobile bundle.

### Authorization test cases

-   Missing token, malformed token, expired token.
-   Valid user accesses own reminder.
-   User A attempts to read/update/delete User B's reminder.
-   Client sends a forged UID.
-   Disabled/invalid device token.
-   Admin SDK/Firestore permission failure.

------------------------------------------------------------------------

## 6. Firestore design

Finalize collections from the existing Phase 2 domain model and actual
query patterns. Suggested initial layout:

``` text
users/{uid}
  displayName, email (only if needed), createdAt, updatedAt, preferences

users/{uid}/devices/{deviceId}
  fcmToken, platform, updatedAt, active

users/{uid}/reminders/{reminderId}
  trainNumber, trainNameSnapshot (optional), source, destination,
  journeyDate, travelClass, quota, conditionType, threshold,
  targetStatus, enabled, createdAt, updatedAt,
  nextCheckAt, lastCheckedAt, lastAvailability, lastNotificationKey

reminderJobs/{jobId}
  uid, reminderPath, dueAt, status, attempts, leaseUntil, createdAt, updatedAt

availabilityObservations/{observationId}
  reminderPath, checkedAt, normalizedAvailability, resultStatus,
  latencyMs, requestId, retentionExpiresAt

notificationOutbox/{notificationId}
  uid, reminderPath, idempotencyKey, title, body, status,
  attempts, createdAt, sentAt, lastErrorCode
```

This is a starting proposal, not a command to duplicate data
unnecessarily. Keep user-owned reminders under `users/{uid}` where
practical. Global worker collections must be server-write-only and
contain only fields workers need.

### Firestore rules and access model

-   Mobile client may read/update only explicitly permitted fields under
    its own user document and devices/reminders, if direct client access
    is required.
-   Prefer backend-only writes for reminder evaluation, observations,
    jobs, and notification outbox.
-   Deny all access by default; write explicit rules and test with the
    Firebase Emulator Suite.
-   Never rely on Firestore rules alone for server-side operations; the
    Admin SDK bypasses rules, so backend ownership checks are mandatory.
-   Avoid storing repeated sensitive data or every raw upstream payload.
-   Add composite indexes only for implemented queries; commit index
    definitions.
-   Use transactions or conditional writes for state transitions and
    deduplication.
-   Define TTL/retention for observations and delivery logs; do not
    depend on TTL for immediate correctness.

### Local testing

Use Firestore Emulator and Firebase Auth Emulator where feasible. Tests
should not connect to production by accident. Require an explicit
environment flag and separate project identifiers for any non-emulator
test.

------------------------------------------------------------------------

## 7. Domain and reminder rules

Initial reminder conditions: 1. **Threshold:** Notify when the returned
RAC count satisfies the user's configured condition, such as `RAC < 12`.
2. **Status transition:** Notify when status changes from `RAC` to
`AVL`. 3. Design condition types so more can be added without rewriting
the scheduler.

Clarify from the verified availability schema exactly what represents
RAC count/status. Never infer RAC count from unrelated fields.

Rules: - Define threshold inclusivity precisely (`< 12` means 11 or
lower). - A transition rule requires a prior valid observation and a new
valid observation. - An upstream error or malformed response is not an
availability observation and must not trigger a false transition. -
Persist last valid observation and last notification idempotency key. -
Define re-arm behavior: whether a condition can notify again after
becoming false and true later. Default to one notification per reminder
per qualifying transition until the user re-arms or edits the reminder,
unless the product decision says otherwise. - Validate journey date,
class, quota, thresholds, reminder ownership, active limits, and
supported rule type. - Show the user the reminder's active/paused state
and last check status.

------------------------------------------------------------------------

## 8. Scheduling, queue, and worker design

1.  A managed scheduler triggers a dispatcher at the approved cadence.
2.  Dispatcher queries only due, enabled reminders or uses a due-job
    collection designed for scalable indexed queries.
3.  It enqueues bounded tasks; avoid a single unbounded task for all
    users.
4.  Worker claims a task using a lease/transaction to prevent concurrent
    processing.
5.  Worker calls the existing availability adapter with timeouts.
6.  On a valid response, normalize required fields, save observation,
    and evaluate rules.
7.  If a condition becomes true, atomically create a notification-outbox
    record with an idempotency key.
8.  Notification sender delivers via FCM and updates delivery state.
9.  Transient failures retry with bounded exponential backoff and
    jitter; permanent failures become visible terminal states.
10. Expired leases can be recovered by a cleanup/reconciliation process.

Avoid one Cloud Scheduler job per reminder. Define queue concurrency,
retry limits, maximum active reminders per user, upstream request
budget, and backpressure. If upstream API quota cannot support the
requested monitoring volume, tell the user and implement sensible limits
rather than polling aggressively.

------------------------------------------------------------------------

## 9. Mobile app implementation

### Screens

1.  **Sign-in:** Google Sign-In, loading/error states, privacy/terms
    links if supplied.
2.  **Search landing:** From, To, swap, DOJ, class, quota, Search
    Trains.
3.  **Station selector/autocomplete:** debounced suggestions and
    selection by station object.
4.  **Results:** train name/number, relevant route/timing data from
    response, class buttons/chips.
5.  **Availability:** exact returned status/counts, last-updated time,
    refresh affordance with rate protection.
6.  **Create reminder:** condition type, threshold or target transition,
    selected train/date/class.
7.  **My reminders:** list, status, pause/resume, edit where supported,
    delete confirmation.
8.  **Settings:** notification permission, device registration state,
    sign-out.
9.  **Error/empty states:** clear recovery guidance without exposing
    stack traces.

### UI/API behavior

-   Station autocomplete cancels or ignores stale responses.
-   Prevent duplicate Search taps and show loading state.
-   Validate DOJ and format only at the API boundary.
-   Do not display fake values for missing fare/timing/availability.
-   Preserve the selected train, date, class, and quota when navigating
    to availability/reminders.
-   Register/refresh FCM token securely; handle permission denied and
    token rotation.
-   Notifications deep-link to the relevant reminder/availability screen
    when feasible.
-   UI must not include booking/payment affordances.

------------------------------------------------------------------------

## 10. API contract for the TrainWatch backend

Use the existing Phase 3 API conventions and avoid adding duplicate
endpoints. Suggested logical routes if not already defined:

-   `GET /healthz` and `GET /readyz`
-   `GET /me`
-   `GET /stations/search?q=...`
-   `GET /trains/search?from=...&to=...&date=...&travelClass=...&sortBy=fare`
-   `POST /trains/availability`
-   `POST /reminders`
-   `GET /reminders`
-   `GET /reminders/{id}`
-   `PATCH /reminders/{id}` for supported changes/pause/resume
-   `DELETE /reminders/{id}`
-   `PUT /devices/{deviceId}` to register/update token
-   `DELETE /devices/{deviceId}` to revoke/remove device
-   Internal, authenticated service-only worker endpoints as needed.

These are proposed logical routes, not a requirement to change an
already implemented API. Keep public mobile APIs versioned if the
existing project convention uses versioning. Validate request/response
models with Pydantic and return stable error shapes. Never expose raw
upstream payloads by default.

------------------------------------------------------------------------

## 11. Implementation phases

### Phase 0 --- Baseline/repository safety --- COMPLETED

Preserve existing baseline, repository safeguards, and records.

### Phase 1 --- Existing API contract research --- COMPLETED

The user has already verified the availability endpoint contract and
response schema. Reuse the verified artifacts.

### Phase 2 --- Domain/data design --- COMPLETED

Preserve existing domain decisions and artifacts. Extend only for a
documented concrete gap.

### Phase 3 --- FastAPI/auth boundary --- COMPLETED

Preserve existing implementation and tests.

### Phase 4 --- Firestore repositories and emulator setup

-   Inspect current repo without changing completed phases.
-   Implement repository interfaces and Firestore adapters.
-   Add emulator configuration, security rules, indexes, and
    deterministic test fixtures.
-   Keep production Firestore unreachable in unit tests. **Exit gate:**
    repository tests, rules tests, ownership tests, and schema/index
    docs pass.

### Phase 5 --- Existing train API integration adapters

-   Implement station search, train search, and availability clients.
-   Map station selection, date format, class/quota codes, and response
    DTOs.
-   Use verified availability contract and read-only source inspection
    if needed.
-   Add timeouts, bounded retries for safe failures, structured errors,
    and mocked contract tests. **Exit gate:** tests cover normal, empty,
    partial, malformed, timeout, 4xx, and 5xx responses; no live API
    calls by default.

### Phase 6 --- Reminder domain and API

-   Implement CRUD/pause/resume, input validation, authorization, and
    pure condition evaluators.
-   Add threshold and RAC→AVL transition rules, plus notification re-arm
    semantics. **Exit gate:** tests cover all rule boundaries,
    cross-user access, duplicates, missing data, and invalid inputs.

### Phase 7 --- Scheduler, queue, and workers

-   Implement dispatcher, due-job querying, Cloud Tasks enqueueing,
    worker claim/lease, retry/backoff, reconciliation, and idempotency.
-   Keep worker concurrency within upstream quota. **Exit gate:**
    duplicate tasks and concurrent workers do not duplicate
    observations/transitions/notifications; failures recover safely.

### Phase 8 --- Notification outbox and FCM

-   Implement outbox persistence, sender, token lifecycle, delivery
    states, and deep links.
-   Use fake sender in tests. **Exit gate:** exactly one logical
    notification per idempotency key; no real FCM in tests.

### Phase 9 --- Security, reliability, and observability

-   Add rate limits, timeouts, structured logs/metrics, request IDs,
    health/readiness checks, dependency scanning, secret scanning, and
    authorization coverage.
-   Define retention, backups/recovery expectations, alerting, and
    incident/runbook guidance. **Exit gate:** security tests and scans
    documented; no secrets in logs; operational failure modes are
    documented.

### Phase 10 --- Staging infrastructure and cost review

-   Produce deployment configuration/IaC for a separate staging
    project/environment.
-   Include least-privilege service accounts, Secret Manager, Firestore
    indexes, Scheduler/Tasks, FCM, budgets, logging, and rollback.
-   Present exact resource list, permissions, and estimated cost before
    provisioning. **Exit gate:** user reviews/approves resources and
    costs. No provisioning without approval.

### Phase 11 --- Staging deployment and live integration tests

-   Deploy only after explicit approval.
-   Configure credentials through Secret Manager or secure environment
    configuration.
-   Run controlled API tests against the existing train endpoint and
    staging Firestore.
-   Test real FCM only with an explicitly approved test device. **Exit
    gate:** evidence for sign-in, search, availability, reminder
    evaluation, queued checks, notifications, retry/recovery, and no
    cross-user access.

### Phase 12 --- Mobile foundation and authentication

-   Set up app navigation, API client, Firebase Google Sign-In, auth
    state, and token attachment.
-   Add loading/error/empty components and environment config. **Exit
    gate:** sign-in/out, expired-session handling, and protected
    navigation pass on target devices.

### Phase 13 --- Search, availability, and reminders UI

-   Implement reference-inspired landing screen, autocomplete,
    date/class/quota controls, train results, class availability,
    reminder create/list/pause/resume/delete, settings, and notification
    navigation.
-   Keep all values sourced from APIs; no invented availability. **Exit
    gate:** mobile tests and mocked full user journey pass.

### Phase 14 --- End-to-end, performance, accessibility, security

-   Run full staging E2E suite, load/latency checks at agreed scale,
    accessibility review, dependency/security scans, and recovery
    drills.
-   Test upstream outage, Firestore failure, queue backlog, FCM failure,
    duplicate tasks, and expired auth. **Exit gate:** release checklist
    signed off; unresolved high-severity issues explicitly accepted by
    the user.

### Phase 15 --- Production readiness and launch

-   Prepare production rollout, monitoring, budgets, alerting,
    backup/recovery, rollback, and support runbook.
-   Perform production actions only with explicit approval immediately
    before execution. **Exit gate:** user approves production deployment
    and any real notifications, polling, data access, or billable cloud
    changes.

------------------------------------------------------------------------

## 12. Agent execution instructions

The implementation agent must:

1.  **Start with assessment, not edits.** Inspect repository status,
    branches, completed phase artifacts, tests, CI, and current
    architecture. Do not reset, rebase, force-push, overwrite user work,
    or modify completed phases.
2.  Produce a concise phase assessment: completed phases, next
    incomplete phase, proposed file changes, dependencies, acceptance
    criteria, risks, and required credentials/permissions.
3.  Implement one phase at a time. Wait for approval before moving to
    the next phase. Do not interpret "finish the project" as permission
    to bypass phase gates, branch protection, or destructive operations.
4.  Use mocks and emulators by default. Never use production credentials
    in tests or commit credentials. Do not ask the user to paste
    service-account private keys or long-lived secrets into chat;
    provide a secure local/Secret Manager setup path.
5.  When credentials are supplied, first identify what each credential
    grants access to. Use least privilege, separate staging from
    production, and never print secrets in logs or summaries.
6.  Do not create cloud resources, enable billable services, deploy,
    access production user data, invoke live APIs at scale, send real
    push notifications, or change production configuration until the
    user explicitly approves the specific action and cost/risk.
7.  Do not modify or redeploy the existing train service at
    `E:\\Projects\\Dream Destiny v2.0\\transport-service\\train` unless
    explicitly authorized.
8.  Keep changes cohesive and loosely coupled. Prefer a modular monolith
    and clear adapters over unnecessary microservices. Avoid
    overengineering.
9.  For each phase, run relevant unit/integration tests, lint,
    formatting, type checks, security/dependency scans, and build
    checks. Report exact commands and results; never claim a check
    passed if it was not run.
10. Create focused feature branches and PRs following repository policy.
    Never force-push or bypass branch protections. Treat CodeRabbit as
    an extra reviewer, not a security guarantee. Resolve actionable
    findings and rerun checks.
11. Before any migration, destructive change, production data mutation,
    or change to authentication/security rules, explain impact and
    obtain explicit approval.
12. After each phase report: phase and files changed; tests/checks and
    exact results; outstanding risks; PR status; any needed user input;
    next phase proposal. Wait for approval.
13. If a blocker requires user credentials, ask for the minimum required
    permission and provide secure configuration steps. Continue all work
    that can be completed with emulators/mocks while waiting.
14. At the final milestone, provide setup instructions, environment
    variable template with placeholders, Firebase/Google setup
    checklist, Firestore rules/index deployment instructions, cloud
    resource map, CI/CD instructions, test report, known limitations,
    estimated recurring cost drivers, rollback procedure, and end-to-end
    test steps.

## 13. Credential and environment handling

Create `.env.example` with placeholders only, such as: -
`APP_ENV=local` - `API_BASE_URL=https://dream-destiny.cloud.run` -
Firebase project identifiers and public client configuration where
appropriate - server-side credential configuration via Application
Default Credentials or Secret Manager references - emulator host
settings for local tests - task queue/scheduler configuration
placeholders - FCM configuration references

Do not put actual keys in `.env.example`. Ensure `.env`, service-account
JSON, private keys, tokens, and local Firebase configuration containing
secrets are ignored by Git. Mobile Firebase client config is not
equivalent to a server secret, but must still be environment-specific
and protected with Firebase/App Check and API restrictions where
appropriate.

## 14. Final acceptance checklist

The project is complete only when all applicable checks are evidenced:

-   [ ] Google Sign-In works on target device(s); backend verifies
    Firebase ID tokens.
-   [ ] Firestore rules and backend authorization prevent cross-user
    data access.
-   [ ] Station autocomplete uses the deployed station endpoint
    correctly.
-   [ ] Train search uses exact query parameters and date/class mapping.
-   [ ] Class tap calls the existing availability endpoint using the
    verified contract.
-   [ ] App displays only valid fields returned by APIs and handles
    partial responses.
-   [ ] Users can create, list, pause/resume, and delete reminders.
-   [ ] RAC threshold and RAC→AVL rules behave correctly on boundary
    cases.
-   [ ] Scheduler/queue/worker handles retries, duplicate tasks,
    backlog, and recovery.
-   [ ] FCM notifications are deduplicated and target the correct
    user/device.
-   [ ] No booking/payment flow exists.
-   [ ] Emulator/mock tests, CI checks, security scans, and mobile
    builds pass.
-   [ ] Staging E2E test evidence is recorded.
-   [ ] Monitoring, cost limits, retention, backup/recovery, and
    rollback are documented.
-   [ ] Production launch is performed only after explicit user
    approval.

## 15. Immediate next action

Assess the existing repository and artifacts without modifying files.
Confirm that Phases 0--3 are intact, identify the next incomplete phase,
and propose the smallest safe scope for Phase 4. Then wait for approval
before implementing it.
