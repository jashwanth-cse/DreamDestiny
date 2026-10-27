# Antigravity Implementation Specification
## TrainWatch Train Metadata Service: Route Schedule + Weekly Running Days

**Purpose:** Build, validate, and production-harden a service that extracts a train's station route/schedule and weekly running-day pattern from an authorized and technically accessible source such as the Ixigo train page. It must be isolated from existing microservices, especially the production Train Availability Service.

**Primary instruction to the coding agent:** Inspect the actual repository and deployment setup before choosing paths or making changes. Implement the smallest safe solution that meets this specification. Do not claim success without test evidence. Do not deploy to production or modify existing production resources without explicit authorization.

---

## 1. Context and product requirement

The TrainWatch Android app lets a user select a train and then choose only valid source and destination stations that the train serves, in the correct travel order. It also needs the train's weekly operating pattern to help users choose a plausible journey date.

A browser inspection of an Ixigo train page showed a structure similar to:

```html
<div class="runs-on u-ib u-v-align-middle">
  <span class="day">S</span>
  <span class="day fade">M</span>
  <span class="day fade">T</span>
  <span class="day fade">W</span>
  <span class="day fade">T</span>
  <span class="day fade">F</span>
  <span class="day fade">S</span>
</div>
```

The tentative interpretation is that a `.day` element without the `fade` class represents a running day, while `.day.fade` represents a non-running day. This is a **hypothesis to validate**, not a guaranteed provider contract. Confirm the ordering of days, actual DOM behavior, and consistency across multiple train pages before relying on it.

A route schedule may include:
- Train number and name
- Ordered station sequence
- Station name and station code
- Arrival and departure times
- Halt duration
- Distance from origin, when available
- Weekly running days

Provider HTML may change or require JavaScript. The service must detect extraction failures rather than return incomplete data as valid.

## 2. Architecture decision: prefer a separate FastAPI service

### Recommended choice

Create a **new, independently deployable Train Metadata / Route Service**, rather than adding scraping and schedule parsing to the existing Train Availability Service.

Why:
1. **Fault isolation:** scraper failures, HTML changes, blocked requests, or slow pages must not degrade seat-availability requests.
2. **Independent scaling:** route metadata is mostly read-heavy and can be cached; availability lookups have different latency and upstream rate-limit characteristics.
3. **Independent refresh policy:** schedule data can be cached and refreshed on a controlled schedule without coupling it to user availability requests.
4. **Clear responsibility:** the existing availability service remains responsible for availability lookups; the new service owns train route metadata and running days.
5. **Safe rollout:** the new service can be tested and deployed independently, with an additive gateway route only after validation.

### When a module inside the existing service would be acceptable

A separate package inside the existing Train Availability Service is reasonable only if the repository already has a clearly modular architecture, the same deployment lifecycle is intentional, and shared failure/load behavior is acceptable. The default decision for this implementation is a **separate service** because the scraper is an independent and potentially brittle integration.

### Isolation requirements

- Do not refactor or rename existing availability routes.
- Do not change the current availability response schema.
- Do not modify unrelated microservices.
- Do not change shared gateway configuration in the initial implementation unless necessary and explicitly approved.
- Add a new service directory/repository or deployment unit following the existing project's conventions.
- Reuse shared libraries only if they are already stable, versioned, and safe to depend on.
- Do not import internal modules from the availability service across service boundaries.
- Communicate over a documented HTTP API.
- If a gateway route is later added, make it additive and independently reversible.

---

## 3. Mandatory discovery phase before coding

First inspect the workspace and document:

1. Repository layout and the location of the existing Train Availability Service.
2. Current Python, FastAPI, Pydantic, and HTTP client versions.
3. Existing coding style, tests, linting, Docker conventions, environment configuration, and CI.
4. Existing gateway/reverse-proxy structure, but do not modify it yet.
5. Whether there is already a train-search or train-metadata provider.
6. Whether the repository contains train/station datasets that can serve as a fallback.
7. Whether direct retrieval of the Ixigo page returns usable HTML without browser execution.
8. Whether the schedule and running-day information are actually present in the returned HTML or are inserted by JavaScript.
9. The source's terms, access restrictions, robots guidance, and permission for automated access. Do not bypass access controls, CAPTCHAs, authentication, or anti-bot protections. If automated scraping is not permitted or reliable, stop the scraper implementation and propose an authorized source or licensed dataset instead.
10. Existing upstream rate limits and any documented provider usage restrictions.

Produce a short discovery report before major edits. Record the baseline Git status and existing test results. Preserve uncommitted work; do not overwrite user changes.

---

## 4. Functional requirements

### 4.1 Route endpoint

Proposed endpoint:

`GET /api/v1/trains/{train_number}/route`

Example:

`GET /api/v1/trains/06030/route`

Return a normalized, provider-independent route response. Do not expose raw provider HTML to clients.

Example contract:

```json
{
  "success": true,
  "data": {
    "train_number": "06030",
    "train_name": "Example Express",
    "stations": [
      {
        "sequence": 1,
        "station_code": "TEN",
        "station_name": "Tirunelveli",
        "arrival": null,
        "departure": "19:00",
        "halt_minutes": null,
        "distance_km": 0
      },
      {
        "sequence": 2,
        "station_code": "RJPM",
        "station_name": "Rajapalayam",
        "arrival": "22:03",
        "departure": "22:05",
        "halt_minutes": 2,
        "distance_km": 142
      }
    ],
    "running_days": [
      "Sunday"
    ],
    "source": "ixigo",
    "fetched_at": "2026-10-19T12:00:00Z",
    "stale": false
  }
}
```

This is an illustrative schema only. Never hardcode example station data or timestamps. Populate fields only from verified source data. If a value is not available, use `null` or omit it according to the agreed schema.

### 4.2 Station route semantics

- Preserve the order of stations as provided by the source.
- Normalize station codes to uppercase and trim surrounding whitespace.
- Normalize train numbers as strings so leading zeroes are preserved.
- Validate station entries and reject a route with impossible or duplicate sequence ordering.
- Do not silently discard a large part of a route to make parsing pass.
- If the provider provides origin/destination metadata, cross-check it against the first and last valid station when possible.
- Do not assume every train route contains a fixed number of stations.
- Do not invent missing times, station codes, distances, or halt durations.
- Store and expose a data-source identifier and fetch timestamp.
- Document whether station entries represent scheduled stops only or also include pass-through stations. For journey selection, only offer boarding/alighting stations that the source identifies as valid stops unless verified data supports a broader rule.

### 4.3 Weekly running days

- Parse the seven day elements only after validating their actual order.
- Do not assume `S M T W T F S` means Sunday-first without verifying the page.
- Determine running days by inspecting the element classes. Initially, treat the absence of `fade` as a candidate active day, but validate this against multiple trains and the rendered page.
- Validate exactly seven day elements are present. If there are fewer, more, or ambiguous labels, fail extraction with a typed parse error.
- Do not infer running days from a single screenshot.
- Represent days using a stable format. Preferred API format: ISO weekday integers (`1=Monday` through `7=Sunday`) plus human-readable labels, or a documented list of weekday names. Pick one format and use it consistently.
- Keep a fixture for a verified HTML sample, with the source and retrieval date documented.
- Handle temporary special services and exceptions as unsupported unless the source explicitly exposes them. A weekly pattern does not guarantee operation on a specific date.

### 4.4 Optional train metadata endpoint

Only implement a train-search/suggestion endpoint if the source has been verified and its schema is stable enough:

`GET /api/v1/trains/search?q=06030&limit=10`

Requirements:
- Support train number and name search.
- Bound `q` length and `limit`.
- Debounce requests in the client; server-side rate limit if public access requires it.
- Return canonical train number, name, and only verified summary metadata.
- Do not scrape a new page for every keystroke. Use an authorized index/dataset or a controlled, cached provider integration.
- If train search is out of scope for the route proof of concept, document it as a later phase rather than inventing an endpoint.

---

## 5. Scraper implementation

### 5.1 Fetching

- Use the project's supported async HTTP client, preferably a reusable `httpx.AsyncClient` managed through FastAPI lifespan.
- Use a fixed, allowlisted provider host and construct URLs from validated train numbers. Never accept arbitrary user-supplied URLs.
- Use HTTPS with certificate verification enabled.
- Set explicit connect, read, write, and pool timeouts where supported.
- Set a conservative connection limit and bounded concurrency.
- Set a reasonable response-size limit and reject unexpectedly large pages.
- Check HTTP status codes and content type before parsing.
- Do not log sensitive headers, cookies, or full raw pages by default.
- Do not use browser automation unless direct HTML has been proven insufficient, permitted, and necessary.
- Do not evade provider anti-bot measures, rotate identities to bypass limits, or bypass access controls.
- Respect upstream rate limits and terms. If access is blocked or prohibited, use an authorized source instead.

### 5.2 Parsing

- Isolate HTML parsing in a dedicated parser module, separate from HTTP fetching and API routes.
- Use BeautifulSoup with a supported parser dependency if the project allows it.
- Use stable semantic selectors where available. If relying on `.runs-on .day` or schedule-specific CSS classes, document this fragility.
- Validate the DOM structure and required fields before returning success.
- Normalize whitespace, HTML entities, time formats, station codes, and distance values.
- Handle missing, duplicate, reordered, or unexpected nodes safely.
- Keep provider-specific HTML structures behind an adapter so a future provider can replace it without changing the API contract.
- Store sanitized fixtures for regression tests. Do not commit personal data, cookies, credentials, or unnecessary raw page content.
- If the page uses JavaScript to populate the schedule, document this and assess whether an authorized structured source exists before adding a browser dependency.

### 5.3 Failure semantics

Use typed internal errors, such as:
- `InvalidTrainNumber`
- `TrainNotFound`
- `ProviderTimeout`
- `ProviderRateLimited`
- `ProviderUnavailable`
- `ProviderBlocked`
- `RouteParseError`
- `RunningDaysParseError`
- `InvalidProviderPayload`

Map them to predictable HTTP status codes:
- `400` for malformed input.
- `404` for a verified unknown train.
- `422` for valid syntax but unsupported/invalid train identifier, if that distinction is documented.
- `429` for client rate limiting.
- `502` for malformed or unexpected upstream responses.
- `503` for provider unavailability or blocked access where appropriate.
- `504` for upstream timeout.

Never translate an upstream failure into an empty station list or a successful response with invented running days. Return a stable error schema without leaking stack traces or internal details.

---

## 6. Caching and data freshness

Route metadata is a good candidate for shared caching because it changes less frequently than live availability.

Implement a cache only after reviewing existing infrastructure. Prefer a shared cache/database if one already exists and is suitable. For the initial service, a small persistent store or Redis may be appropriate if operationally available; otherwise, a bounded in-memory TTL cache may be used only as a per-instance optimization, never as the authoritative cross-instance cache.

Requirements:
- Use a configurable TTL.
- Cache successful, validated route responses.
- Use a short negative-cache TTL only for verified `404` results.
- Do not cache transient upstream failures as valid data.
- Prevent a burst of identical cache misses from triggering many upstream requests (single-flight/request coalescing).
- Bound cache size if in-memory caching is used.
- Include `fetched_at` and `stale` in the response.
- Define stale-on-error behavior explicitly. If stale data is returned, label it as stale and preserve its original timestamp.
- Never return stale data as current without marking it.
- Do not refresh on every user request.
- Consider a background refresh job only after defining the operational mechanism and permitted fetch frequency.
- Cache keys must include the normalized train number and any other relevant source/locale/version dimensions.
- Avoid per-user cache keys for public train metadata.

Suggested starting configuration, to be tuned using evidence:
- Connect timeout: 3 seconds.
- Read timeout: 8 seconds.
- Overall upstream deadline: 10 seconds.
- Route metadata TTL: 6–24 hours, subject to source change frequency and terms.
- Negative cache TTL: 1–5 minutes for verified not-found results only.
- In-flight fetch concurrency: conservative and configurable.

These are initial design values, not measured capacity claims. Validate and tune them in staging.

---

## 7. Statelessness and concurrency

The service must be safe to run with multiple Uvicorn workers, containers, and instances.

- No correctness dependency on process-local mutable state.
- No shared mutable per-request parser/result objects.
- Reuse a correctly managed HTTP connection pool.
- Use bounded upstream concurrency.
- Add in-flight request coalescing for identical route lookups if justified.
- If using in-memory caching, document that it is local optimization only and can differ across instances.
- If using a distributed cache or shared persistence, configure connection timeouts and failure behavior.
- Ensure cancellation and client disconnects do not leak tasks or connections.
- Ensure lifespan startup/shutdown closes clients and cache connections.
- Do not create a new `AsyncClient` per request.
- Do not use unbounded `asyncio.gather`, background task creation, or unbounded queues.
- Do not use in-process locks as if they were distributed locks.
- If a distributed lock is truly required, justify it and use safe lease/expiry semantics.

The service must not depend on the existing availability service's process memory, database schema, or internal modules.

---

## 8. Security and abuse resistance

- Validate `train_number` against a strict allowlist of expected characters and length.
- Preserve leading zeroes.
- Prevent SSRF by not accepting arbitrary hostnames or URLs.
- Use outbound HTTPS with certificate verification.
- Add sensible request rate limiting at the gateway or service boundary, depending on the deployment.
- Set request and response size limits.
- Avoid exposing raw provider HTML or internal exception messages.
- Keep secrets in environment configuration or the project's approved secret manager.
- Do not commit credentials or cookies.
- Ensure production debug mode is disabled.
- Review CORS only if browser clients need it; do not use wildcard CORS with credentials.
- Scan dependencies with the project's approved tool and report findings.
- Do not make production changes or run destructive tests without approval.

---

## 9. Observability and operational readiness

Provide:
- `/health/live`: confirms the process is alive without contacting Ixigo.
- `/health/ready`: checks that required local dependencies are usable. It should not scrape a train page on every probe.
- Structured logs with request/correlation IDs.
- Metrics for request count, latency, HTTP status, cache hits/misses, upstream latency/status, parse failures, timeout count, in-flight fetches, and stale responses.
- Avoid train-specific high-cardinality metric labels.
- Never log secrets or complete raw provider responses by default.
- A clear startup/shutdown lifecycle.
- Configurable log level and timeouts.
- A documented runbook for provider HTML changes and upstream failures.

Do not add Prometheus or another infrastructure dependency if the platform already provides a standard observability system; follow the repository conventions.

---

## 10. End-to-end and concurrent testing plan

Testing must use recorded, sanitized fixtures and mocked upstream responses for deterministic CI. Real-source verification should be a separately controlled smoke test, run only if access is permitted and at a conservative rate.

### 10.1 Parser unit tests

Cover:
- Valid route with all fields.
- Missing optional arrival/departure values.
- Missing or malformed station codes.
- Duplicate or unordered sequence values.
- Missing schedule table.
- Empty HTML.
- Changed CSS classes.
- Missing running-days block.
- Fewer or more than seven weekday elements.
- Ambiguous weekday order.
- All seven days active.
- No days active.
- `fade` class present versus absent.
- Invalid times, distance, or halt values.
- HTML entity and whitespace normalization.
- Unknown or additional fields.

### 10.2 API integration tests

Cover:
- `GET /api/v1/trains/06030/route`.
- Invalid train number.
- Verified not-found response.
- Provider timeout.
- Provider `429`, `403`, `5xx`, malformed JSON if applicable, and malformed HTML.
- Stale cache response after upstream failure.
- Correct error mapping and response schema.
- Health endpoints without upstream requests.
- Cache hit avoids a second provider request.
- Identical simultaneous requests are coalesced if that feature is implemented.

### 10.3 Route semantics tests

Given a verified ordered station list:
- Source and destination must both exist.
- Destination must occur after source.
- Same source and destination is invalid.
- Reverse direction must be rejected for a one-direction train instance.
- Unknown station code must be rejected.
- The service returns canonical station names and codes.
- The app can derive eligible destinations from the route sequence.

If implementing a journey-validation endpoint, make it a small pure domain function first. Only expose a new API route if the client genuinely needs server-side validation.

### 10.4 Concurrency tests

Create deterministic local tests that run many concurrent requests against the app using mocked upstream calls. Include:
- 1, 10, 50, and 100 concurrent requests.
- Many requests for the same train.
- Requests for different train numbers.
- Mixed valid and invalid requests.
- Slow upstream responses and timeouts.
- Cache warm and cache cold scenarios.
- Simulated provider failures during concurrency.

Assertions:
- No cross-request data leakage.
- No malformed or mixed train identifiers.
- No unbounded number of upstream requests.
- Identical requests are coalesced when expected.
- Connection/resource counts remain bounded.
- Errors remain correctly isolated.
- Response schemas stay valid.

Do not equate a local 100-request test with proof of 10,000 concurrent production capacity. Use staged load tests with realistic latency, instance count, worker configuration, and monitoring before making a capacity claim.

### 10.5 End-to-end tests

Run the following flow against local or authorized staging infrastructure:

1. Start the service with a deterministic fixture/mock provider.
2. Request the route for train `06030`.
3. Validate station order and running days against the verified fixture.
4. Select Rajapalayam (`RJPM`) as source and Coimbatore Junction (`CBE`) as destination.
5. Validate that the destination occurs after the source.
6. Confirm an invalid or reverse-order journey is rejected.
7. Repeat the request to confirm cache behavior.
8. Simulate an upstream outage and verify error/stale semantics.
9. Run concurrent requests and inspect request counts, latency, and errors.
10. Confirm the existing Train Availability Service still passes its original regression tests and its public contract is unchanged.

Do not hit the production upstream for bulk tests. A live smoke test should make only a small number of requests, subject to access permission and rate limits.

### 10.6 Performance report

For each load test, report:
- Concurrency level.
- Total request count.
- Duration.
- Requests per second.
- p50, p95, and p99 latency.
- Error rate and error categories.
- Cache hit rate.
- Upstream calls per API request.
- CPU/memory where available.
- Test environment and worker/instance settings.

Do not fabricate results. If a measurement cannot be collected, state that clearly.

---

## 11. Suggested project structure

Adapt this to the actual repository conventions rather than blindly creating duplicate scaffolding.

```text
train-metadata-service/
├── app/
│   ├── main.py
│   ├── api/
│   │   └── routes.py
│   ├── schemas/
│   │   └── route.py
│   ├── domain/
│   │   ├── models.py
│   │   └── journey_validation.py
│   ├── providers/
│   │   ├── base.py
│   │   └── ixigo.py
│   ├── services/
│   │   └── route_service.py
│   ├── parsers/
│   │   └── ixigo_schedule.py
│   ├── cache/
│   │   └── interface.py
│   ├── config.py
│   └── errors.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── concurrency/
│   └── e2e/
├── Dockerfile
├── pyproject.toml
├── .env.example
├── README.md
├── TRAIN_METADATA_AUDIT.md
└── TRAIN_METADATA_OPERATIONS.md
```

Use interfaces only where they create a real replaceable boundary. Do not create empty modules or abstraction layers solely to match this tree.

---

## 12. API contract details

### Route response

Use Pydantic models and a consistent envelope. Suggested fields:

- `success`: boolean.
- `data.train_number`: string.
- `data.train_name`: string or `null`.
- `data.stations`: ordered array.
- `data.running_days`: stable documented representation.
- `data.source`: provider identifier.
- `data.fetched_at`: ISO-8601 timestamp in UTC.
- `data.stale`: boolean.
- Optional `data.warnings`: non-sensitive extraction caveats.

Each station may contain:
- `sequence`: positive integer.
- `station_code`: string or `null` only if the contract permits it.
- `station_name`: non-empty string.
- `arrival`: time string or `null`.
- `departure`: time string or `null`.
- `halt_minutes`: non-negative integer or `null`.
- `distance_km`: numeric value or `null`.

Use a consistent error envelope such as:

```json
{
  "success": false,
  "error": {
    "code": "PROVIDER_TIMEOUT",
    "message": "Train route data is temporarily unavailable.",
    "request_id": "correlation-id"
  }
}
```

Do not return internal stack traces, raw upstream bodies, or sensitive request headers.

### Optional journey validation

If useful, add:

`GET /api/v1/trains/{train_number}/journeys/validate?source=RJPM&destination=CBE`

Only add this endpoint if the app needs a server-side validation call. It should use the cached route data and validate that both stations exist and that the destination sequence is greater than the source sequence. Prefer keeping this rule in a reusable domain function so the API and tests share the same behavior.

---

## 13. Deployment plan

1. Implement and test the new service locally.
2. Run linting, type checks, dependency scanning, unit tests, integration tests, and concurrency tests.
3. Build a container using the repository's existing conventions.
4. Run it locally with the same Python/runtime configuration intended for staging.
5. Deploy only to a separate staging service/container/port.
6. Verify health endpoints, logs, resource usage, cache behavior, and API contract.
7. Run a conservative live-source smoke test only if permitted.
8. Perform a controlled staging load test.
9. Document how to roll back the new service.
10. Only after explicit approval, add an additive gateway route and deploy independently.

Do not change the existing availability service deployment, shared environment variables, shared database schema, or unrelated microservices as part of this implementation.

If an existing repository is a monorepo, place the new service in a separate directory with its own dependency and deployment configuration. Confirm the CI/CD pipeline does not accidentally rebuild or redeploy unrelated services.

---

## 14. Required deliverables

Create these documents and code changes:

### `TRAIN_METADATA_AUDIT.md`
Include:
- Discovery findings.
- Whether direct HTTP retrieval contains schedule and running-day data.
- Evidence for the DOM selectors and weekday order.
- Source access/terms assessment and any unresolved restrictions.
- Known limitations and provider fragility.
- Security and scalability risks.

### `TRAIN_METADATA_OPERATIONS.md`
Include:
- Environment variables (names only, no secret values).
- Local startup and shutdown.
- Health/readiness checks.
- Cache and TTL behavior.
- Timeout/concurrency settings.
- Logging and metrics.
- Troubleshooting HTML structure changes.
- Staging deployment and rollback instructions.

### `README.md`
Include:
- Service purpose and architecture.
- API usage and sample responses clearly marked as illustrative.
- Local setup and test commands.
- Configuration and operational assumptions.

### Code and tests
Implement the new service, route parser, running-day extraction, normalized API, cache behavior if justified, typed errors, and automated tests. Include a controlled concurrency test and end-to-end flow.

### Final implementation report
Summarize:
- Architecture decision and why.
- Files created/modified.
- Endpoints implemented.
- Test commands and actual outcomes.
- Concurrency test measurements.
- Dependency scan results.
- Existing Train Availability Service regression results.
- Any blocked work or unresolved risks.
- Explicit readiness verdict: `Ready for staging`, `Not ready`, or `Ready for production with evidence`.

---

## 15. Acceptance criteria

The implementation is not complete until:

- [ ] Existing Train Availability Service code and contract are unchanged, except for separately approved additive integration.
- [ ] The new service is independently deployable.
- [ ] Direct page retrieval and permission for automated access are assessed.
- [ ] The parser extracts verified station route data and running days, or fails safely with a documented reason.
- [ ] The running-day order and `fade` semantics are validated across multiple samples.
- [ ] Missing or changed HTML cannot produce fabricated success data.
- [ ] The route preserves station sequence and canonical station codes.
- [ ] Source/destination order validation is tested.
- [ ] Timeouts, response-size limits, and bounded concurrency are configured.
- [ ] Cache behavior and freshness semantics are explicit.
- [ ] Multiple instances do not rely on local state for correctness.
- [ ] Unit, integration, failure-injection, concurrency, and end-to-end tests run.
- [ ] Existing service regression tests pass, or any pre-existing failures are documented.
- [ ] Performance measurements are real and reproducible.
- [ ] No production deployment or unrelated infrastructure change occurred without approval.
- [ ] Documentation and rollback instructions are complete.

## 16. Final instruction to Antigravity

Start with repository discovery and a baseline. Validate whether the provider page can be accessed and parsed reliably and lawfully. Then implement the separate Train Metadata Service with a provider adapter, robust parsing, normalized API, caching where justified, and automated tests.

Do not silently assume the screenshot's HTML class convention is stable. Do not bypass restrictions. Do not change existing microservices. Do not claim 10,000-concurrent-user readiness from a small local test. Deliver working code, exact test evidence, documented limitations, and a clear readiness verdict.
