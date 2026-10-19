# Transport Service - Train Domain

A production-ready FastAPI microservice for searching trains, stations, and real-time IRCTC seat availability.

## Folder Structure

```text
train/
├── app/
│   ├── main.py                     # FastAPI application, lifespan, middlewares, health/readiness
│   ├── config.py                   # Centralized configuration, dynamic headers, and timeouts
│   ├── routes/
│   │   ├── stations.py             # Endpoints for stations
│   │   ├── trains.py               # Endpoints for trains search and multi-tier route fallback
│   │   └── availability.py         # Endpoints for live train availability and fares
│   ├── services/
│   │   ├── station_service.py      # Station resolution (local index + API fallback)
│   │   ├── train_service.py        # Train search logic & live availability enrichment
│   │   ├── availability_service.py # Facade with singleflight deduplication & semaphore bounds
│   │   ├── availability_provider.py# Upstream ConfirmTkt/Ixigo provider with async client & retries
│   │   ├── circuit_breaker.py      # In-process circuit breaker (fail-fast on outages)
│   │   └── route_fallback_service.py # 3-level route fallback hierarchy
│   ├── models/
│   │   ├── availability_models.py  # Pydantic v2 strict request & response models
│   │   └── response_models.py      # Domain responses (Stations, Trains, Classes)
│   ├── utils.py                    # Generic text parsing and normalization helpers
│   └── exceptions.py               # Typed domain exceptions (Timeout, Connection, CircuitBreaker)
├── scripts/
│   └── load_test_availability.py   # Repeatable async concurrency & singleflight benchmark
├── tests/
│   ├── test_availability_service.py # Comprehensive availability, validation, concurrency tests
│   ├── test_availability_enrichment.py # Tests for search availability enrichment
│   ├── test_railway_station_resolver.py# Tests for offline station resolver
│   └── test_route_fallback.py      # Tests for 3-tier division/state route fallback
├── requirements.txt
├── Dockerfile
├── README.md
├── TRAIN_SERVICE_AUDIT.md          # Comprehensive audit report
├── TRAIN_SERVICE_REFACTOR_PLAN.md  # Architectural refactoring plan
├── TRAIN_SERVICE_OPERATIONS.md     # Production operations & runbook
└── .env.example
```

## Key Architectural Enhancements (v2.0)

1. **Non-Blocking Asynchronous I/O**: Upstream ConfirmTkt API calls use `httpx.AsyncClient` with keep-alive connection pooling, eliminating asyncio event-loop starvation.
2. **In-Flight Request Coalescing (Singleflight)**: Duplicate concurrent requests for the same `(train_no, source, dest, class, date, quota)` are collapsed into a single upstream request, shielding upstream providers and avoiding HTTP 429 rate limits.
3. **Circuit Breaker**: Trips to `OPEN` after 5 consecutive upstream timeouts or 5xx errors to prevent cascading failures, recovering automatically via `HALF_OPEN` probe.
4. **Resilient Retries**: Automatic bounded retries (up to 2 attempts) with exponential backoff and randomized jitter for transient errors (429, 502, 503, 504).
5. **Strict Input Validation**: Validates 4-5 digit train numbers, 2-5 letter uppercase station codes, IRCTC travel classes, and 120-day reservation windows.
6. **Correlation ID Tracking**: Every request generates or propagates `X-Correlation-ID` across structured logs and response headers.
7. **Readiness Probe**: Dedicated `GET /ready` probe verifies that the offline dataset index is warmed before routing traffic.

## Available Endpoints

### 1. Liveness Check
`GET /health`  
Returns sub-millisecond status with zero external dependencies.

### 2. Readiness Check
`GET /ready`  
Returns status and verifies that the station dataset index (8,600+ stations) is loaded.

### 3. Live Train Availability
`POST /api/v1/trains/availability`  
Fetch live IRCTC seat availability, fares, and predictions for a train and travel class.

**Calling Conventions (Both Supported):**
- **Query Parameters**:
  ```http
  POST /api/v1/trains/availability?trainNo=16102&source=RJPM&destination=SVKS&travelClass=SL&date=26-08-2026&quota=GN
  ```
- **JSON Request Body**:
  ```json
  POST /api/v1/trains/availability
  Content-Type: application/json

  {
    "trainNo": "16102",
    "source": "RJPM",
    "destination": "SVKS",
    "travelClass": "SL",
    "date": "26-08-2026",
    "quota": "GN"
  }
  ```

**Success Response (HTTP 200):**
```json
{
  "success": true,
  "message": "Live availability fetched",
  "data": {
    "train_number": "16102",
    "travel_class": "SL",
    "quota": "GN",
    "availability": "AVL 25",
    "booking_status": "AVAILABLE",
    "prediction": 95,
    "fare": 140,
    "total_fare": 175,
    "booking_enabled": true,
    "last_updated": "2026-10-18T10:00:00",
    "next_available_dates": ["27-08-2026"]
  }
}
```

### 4. Search Stations
`GET /api/v1/stations/search?q=rajapalayam`

### 5. Search Trains
`GET /api/v1/trains/search?from=Rajapalayam&to=Chennai&date=24-07-2026&travelClass=3A&sortBy=fare`

## Running Automated Tests

```bash
cd transport-service/train
pytest -v
```

## Running Concurrency Benchmark

```bash
python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 100 --concurrency 20
```
