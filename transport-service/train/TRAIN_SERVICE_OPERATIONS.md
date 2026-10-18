# Production Operations & Runbook — Train Availability Microservice
**Project:** Dream Destiny v2.0 — Transport Service (Train Domain)  
**Document:** Operations Guide, Configuration & Runbook  
**Audience:** Site Reliability Engineers (SRE), DevOps & Backend Engineers  
**Date:** October 18, 2026  
**Service Version:** 2.0.0  

---

## 1. Environment Variables & Configuration

The service is configured via environment variables. In the absence of environment variables, hardened production defaults are applied automatically.

| Variable Name | Default Value | Description |
|---|---|---|
| `APP_ENV` | `development` | Set to `production` in production to disable OpenAPI `/docs`, `/redoc`, and `/openapi.json`. |
| `PORT` | `8005` | Microservice port (mapped to 8005 in `docker-compose.yml`). |
| `FRONTEND_ORIGIN` | `https://dreamdestiny.duckdns.org` | Allowed CORS origins (comma-separated for multiple origins). |
| `CONFIRMTKT_AVAILABILITY_API` | `https://ixigotrainsapi.confirmtkt.com/api/v1/availability/fetchAvailability` | Upstream live availability endpoint. |
| `CONFIRMTKT_API_KEY` | *(Internal default)* | Upstream client API key. |
| `CONFIRMTKT_CLIENT_ID` | `iximweb` | Upstream client ID. |
| `UPSTREAM_CONNECT_TIMEOUT` | `5.0` | Upstream socket connect timeout in seconds. |
| `UPSTREAM_READ_TIMEOUT` | `15.0` | Upstream socket read/response timeout in seconds. |
| `UPSTREAM_WRITE_TIMEOUT` | `5.0` | Upstream socket write timeout in seconds. |
| `UPSTREAM_POOL_TIMEOUT` | `5.0` | Connection pool wait timeout in seconds. |
| `MAX_KEEPALIVE_CONNECTIONS` | `20` | Max idle keep-alive connections in HTTP connection pool. |
| `MAX_CONNECTIONS` | `50` | Max total concurrent outbound HTTP connections. |
| `MAX_CONCURRENT_AVAILABILITY` | `15` | Max concurrent upstream availability queries per worker process. |
| `AVAILABILITY_MAX_RETRIES` | `2` | Max retry attempts for transient upstream failures (429, 502, 503, 504). |
| `AVAILABILITY_BACKOFF_FACTOR` | `0.3` | Base exponential backoff factor in seconds. |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD`| `5` | Number of consecutive upstream failures before circuit trips to `OPEN`. |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | `15.0` | Duration in seconds the circuit remains `OPEN` before testing recovery. |
| `RAILWAY_STATIONS_DATA_PATH` | `/app/data/railway_stations.json` | Path to IRCTC preprocessed railway stations dataset. |

---

## 2. Startup, Lifespan & Graceful Shutdown

### Startup Sequence
1. **Resolver Warmup**: During FastAPI's `lifespan` startup, `_ensure_resolver_loaded()` loads `data/railway_stations.json` into memory (8,600+ IRCTC stations, exact, code, and alias indexes). This guarantees sub-millisecond local station lookups with zero network calls.
2. **Connection Pools Initialized**: `httpx.AsyncClient` initializes its bounded connection pool with TCP keep-alive.
3. **Readiness Probe Opens**: Once datasets are in memory, `GET /ready` returns `HTTP 200 {"status": "ready"}`.

### Graceful Shutdown Sequence
1. Incoming traffic is drained by Nginx reverse proxy.
2. FastAPI `lifespan` context exits.
3. `AvailabilityService.aclose()` drains active in-flight requests and closes the `httpx.AsyncClient` connection pool, releasing sockets cleanly without connection resets.

---

## 3. Health & Readiness Probes

The microservice provides distinct liveness and readiness probes designed for container orchestrators (Docker, Kubernetes) and Nginx upstream monitors.

### 1. Liveness Probe (`GET /health`)
- **Purpose**: Verify the Python process and event loop are responsive.
- **Dependencies**: Zero external dependencies, zero disk I/O, zero network calls.
- **Response**: `HTTP 200 OK`
  ```json
  {
    "status": "healthy",
    "service": "dream-destiny-train",
    "version": "2.0.0"
  }
  ```
- **SLA**: < 1ms response time.

### 2. Readiness Probe (`GET /ready`)
- **Purpose**: Verify the local dataset is fully indexed in memory before traffic is routed to the instance.
- **Dependencies**: In-memory station resolver.
- **Response (Ready)**: `HTTP 200 OK`
  ```json
  {
    "status": "ready",
    "service": "dream-destiny-train",
    "total_stations": 8614
  }
  ```
- **Response (Not Ready)**: `HTTP 503 Service Unavailable`
  ```json
  {
    "status": "not_ready",
    "reason": "Station dataset loading"
  }
  ```

---

## 4. Logging & Observability

### Correlation ID Tracking
Every request entering the system is stamped with an `X-Correlation-ID` header.
- If passed by the client or Nginx (`X-Correlation-ID` or `X-Request-ID`), it is preserved.
- If absent, the middleware generates a unique 12-character hexadecimal trace token.
- The correlation ID is included in all log lines and returned in the HTTP response headers.

### Sample Structured Log Entries
```text
2026-10-18 17:10:13,421 [INFO] app.main: [corr_id=a1b2c3d4e5f6] Incoming: POST /api/v1/trains/availability
2026-10-18 17:10:13,425 [INFO] app.services.availability_provider: ConfirmTkt API Request (attempt 1/3): POST ... train=16102, route=RJPM->SVKS, class=SL
2026-10-18 17:10:13,680 [INFO] app.main: [corr_id=a1b2c3d4e5f6] Completed: POST /api/v1/trains/availability - Status: 200 - Time: 259.12ms
```

### Key Metrics to Monitor
1. **HTTP Request Latency**: Monitor p95 and p99 on `POST /api/v1/trains/availability` (target: < 800ms).
2. **Upstream Status Codes**: Track occurrences of upstream 429 (rate-limiting) and 504 (timeouts).
3. **Singleflight Deduplication Ratio**: Ratio of inbound queries to actual outbound ConfirmTkt API calls.
4. **Circuit Breaker State**: Alert immediately if `CircuitState` changes to `OPEN`.

---

## 5. Verification Commands & Local Testing

### Run All Unit & Integration Tests
```bash
cd transport-service/train
pytest -v
```

### Run Tests with Coverage Report
```bash
pytest --cov=app tests/ -v
```

### Execute Concurrency Load Test
Start the local server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8005
```
Run the benchmark script in another terminal:
```bash
python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 100 --concurrency 20
```

---

## 6. Deployment & Rollback Runbook

### Deployment Checklist
1. Verify `docker-compose.yml` mounts `./data:/app/data:ro` for station dataset resolution.
2. Confirm `APP_ENV=production` is set in production environment files.
3. Validate Nginx configuration routes:
   - `location /api/v1/trains { proxy_pass http://train_service; }`
   - `location = /api/v1/trains/health { proxy_pass http://train_service/health; }`
4. Deploy container:
   ```bash
   docker compose build train-service
   docker compose up -d train-service
   ```
5. Confirm container healthcheck:
   ```bash
   docker inspect --format='{{json .State.Health}}' dream-destiny-train
   ```

### Rollback Procedure
If any unexpected upstream incompatibility arises, rollback cleanly:
```bash
# Revert git branch changes
git checkout HEAD~1 -- transport-service/train

# Rebuild and restart container
docker compose build train-service
docker compose up -d train-service
```
