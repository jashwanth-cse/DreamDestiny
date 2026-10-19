# Production Refactoring Plan — Train Availability Microservice
**Project:** Dream Destiny v2.0 — Transport Service (Train Domain)  
**Document:** Refactoring Plan & Target Architecture  
**Author:** Senior Backend Architect, FastAPI Specialist, Application Security Engineer & SRE  
**Date:** October 18, 2026  
**Status:** APPROVED FOR IMPLEMENTATION  

---

## 1. Prioritized Fixes & Implementation Scope

To achieve immediate production readiness while preserving 100% backward compatibility for all existing callers (Nginx, Planner Service, Showcase frontend, and existing test suites), the refactoring is divided into two phases:

### Phase 1: Immediate In-Scope Implementation (Now)
| Priority | Target Component | Fix Description | Finding Reference |
|---|---|---|---|
| **P0 (Critical)** | `app/services/availability_provider.py` & `app/routes/availability.py` | Replace blocking `requests` calls with non-blocking `httpx.AsyncClient` with explicit connection pool limits and timeouts. | **CRIT-01** |
| **P0 (Critical)** | `app/services/availability_service.py` | Implement In-Flight Request Coalescing (Singleflight) and concurrency semaphore to bound upstream load. | **CRIT-02** |
| **P1 (High)** | `app/config.py` | Externalize API credentials to environment variables with fallback defaults; replace static process UUIDs with dynamic request identifiers. | **HIGH-02** |
| **P1 (High)** | `app/models/availability_models.py` | Implement strict Pydantic v2 validation models for requests (regex on trainNo, station codes, ISO/Indian date ranges, IRCTC classes and quotas) and responses. | **HIGH-03**, **LOW-01** |
| **P1 (High)** | `app/routes/availability.py` | Map upstream failures to standard HTTP codes (502/504) with sanitized client error messages; support both query parameters and JSON body. | **HIGH-04**, **LOW-02** |
| **P2 (Medium)** | `app/services/availability_provider.py` | Define `AvailabilityProvider` Protocol/Interface and implement `ConfirmTktProvider` with exponential backoff retries and circuit breaker. | **MED-01**, **MED-03**, **MED-04** |
| **P2 (Medium)** | `app/routes/availability.py` | Inject service dependencies via FastAPI `Depends()`, enabling clean unit testing and mock overrides. | **MED-02** |
| **P3 (Info)** | `app/main.py` | Add Request Correlation ID middleware (`X-Correlation-ID`) and dedicated `/ready` probe; ensure clean lifespan client cleanup. | **INFO-01**, **INFO-02** |

### Phase 2: Future Platform Additions (Later / External Monitoring Service)
- **External Shared Snapshot Cache**: Redis distributed cache with 60–120s TTL if horizontal scaling across multiple container replicas exceeds upstream rate quotas.
- **Seat Alert Subscription Engine**: Dedicated monitoring service with Celery/Temporal workers and Redis watch registries (out of scope for this microservice).

---

## 2. Proposed Architecture & Component Design

```
                                [Inbound Request]
                         POST /api/v1/trains/availability
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │ Correlation ID & Error Middleware │
                     │  - Generates/Extracts X-Request-ID│
                     │  - Structured logging with timing │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │     Pydantic Validation Layer     │
                     │  - trainNo: 5 digits regex        │
                     │  - source/destination: 2-5 chars  │
                     │  - travelClass: SL, 3A, 2A, etc.  │
                     │  - date: DD-MM-YYYY in valid range│
                     │  - quota: GN, TQ, etc.            │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │   AvailabilityService (Facade)    │
                     │  - In-flight Request Coalescing   │
                     │  - Bounded Concurrency Semaphore  │
                     │  - Backward-compatible sync/async │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │   AvailabilityProvider Protocol   │
                     │      (Abstract Interface)         │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │ ConfirmTkt / Ixigo Async Provider │
                     │  - httpx.AsyncClient pool         │
                     │  - Circuit Breaker (Fail-fast)    │
                     │  - Exponential Backoff & Jitter   │
                     │  - Normalized Response Mapping    │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     [Upstream ConfirmTkt API (HTTPS)]
```

### Architectural Details

#### 1. Provider Protocol (`AvailabilityProvider`)
```python
class AvailabilityProvider(Protocol):
    async def fetch_availability(
        self,
        train_no: str,
        source: str,
        destination: str,
        travel_class: str,
        date: str,
        quota: str = "GN",
    ) -> AvailabilityData:
        ...
```
This enables zero-code-change switching to any alternative provider or test fixture.

#### 2. In-Flight Singleflight Coalescing
A thread-safe / asyncio-safe task map:
- Key: `(train_no, source, destination, travel_class, date, quota)`
- If a task for `key` is currently awaiting upstream, subsequent requests register a listener on that exact same `asyncio.Future` or `asyncio.Task`.
- When the response arrives, all waiting requests receive the parsed result simultaneously.
- Peak upstream calls for hot trains drop from $N$ to $1$.

#### 3. Circuit Breaker
- States: `CLOSED` (normal), `OPEN` (tripped after $X$ consecutive upstream timeouts or 5xx), `HALF_OPEN` (testing recovery).
- Trip threshold: 5 consecutive failures.
- Reset timeout: 15 seconds.
- Benefit: Prevents thread/socket exhaustion and protects upstream providers from retry amplification during outages.

#### 4. Backward Compatibility Guarantee
- `TrainService._enrich_availability` in `app/services/train_service.py` calls:
  `_availability_service.fetch_availability(train_no, source, destination, travel_class, date, quota)` synchronously.
  `AvailabilityService` will retain a fully synchronous wrapper `fetch_availability(...)` that returns the exact dictionary structure expected by `TrainService` and `test_availability_enrichment.py`.
- `POST /api/v1/trains/availability` will accept:
  - Query parameters (original contract): `?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date=26-08-2026&quota=GN`
  - JSON body (modern REST contract): `{"trainNo": "16102", "source": "RJPM", "destination": "SVKS", "travelClass": "SL", "date": "26-08-2026", "quota": "GN"}`
- Responses strictly conform to the existing `{ "success": True, "message": "...", "data": { ... } }` schema.

---

## 3. Rationale for Architectural Decisions

1. **Why `httpx.AsyncClient` over `requests`?**
   FastAPI is built on asyncio. Running blocking `requests` inside `async def` halts the single event loop thread for all concurrent requests. `httpx.AsyncClient` uses non-blocking socket I/O, allowing thousands of concurrent requests to be handled efficiently without thread contention.
2. **Why In-Process Singleflight over Redis?**
   Per the audit requirements: *"Do not add Redis, a database, or another persistence layer unless a demonstrated requirement justifies it."* In-process singleflight eliminates duplicate concurrent queries within each worker without introducing network hops or external infrastructure dependencies.
3. **Why Keep Synchronous `fetch_availability`?**
   `TrainService.search` runs synchronously via FastAPI's threadpool (`def search_trains`). Providing both async and sync entry points ensures `TrainService` and all existing unit tests in `test_availability_enrichment.py` continue to pass without modifying their assertions.
4. **Why Strict Regex Validation?**
   IRCTC train numbers are strictly 5 numeric digits. Station codes are 2–5 uppercase letters. Validating these upfront blocks malformed requests, SQL/command injection vectors, and saves upstream API calls.

---

## 4. Risks & Rollback Strategy

| Identified Risk | Likelihood | Impact | Mitigation / Rollback Strategy |
|---|---|---|---|
| Upstream ConfirmTkt API schema drift | Low | Medium | Defensive dictionary access (`.get()`) with fallback defaults for missing fields. Tests cover missing/malformed payloads. |
| Breaking existing test assertions in `test_availability_enrichment.py` | Low | High | Verified baseline tests. Retain identical method signature and dictionary output on `_availability_service.fetch_availability`. |
| Async event loop conflicts in synchronous test runners | Low | Medium | Async methods run cleanly under AnyIO/asyncio; sync fallback handles synchronous callers via `asyncio.run()` or dedicated worker if no loop is running. |

### Rollback Strategy
All code modifications are contained within `transport-service/train`. If any unforeseen regression occurs, Git branch `audit/train-availability` allows instant rollback via:
```bash
git checkout HEAD -- transport-service/train
```

---

## 5. Integration Plan for Future Train Seat-Alert Application

To support a future train seat-alert and monitoring system (e.g. Dream Destiny Seat Alerts):
1. **Shared Watch Registry (In Monitor Service)**:
   The monitoring service groups user subscriptions by `(train_no, source, destination, class, date, quota)` into a deduplicated watch table.
2. **Scheduled Polling**:
   A periodic scheduler triggers batch checks by calling `POST /api/v1/trains/availability` on this microservice.
3. **Change Detection**:
   The monitoring service compares the latest snapshot against the previous state:
   - `AVL -> AVL` (No change)
   - `WL 15 -> WL 5` (Improvement detected -> notify user)
   - `WL 2 -> RAC 1` (Major status upgrade -> trigger urgent notification)
   - `RAC -> AVL` (Seat confirmed available -> trigger booking alert)
4. **Decoupled Architecture**:
   This availability microservice remains purely stateless, highly concurrent, and fast, without knowing about user phone numbers, push tokens, or databases.
