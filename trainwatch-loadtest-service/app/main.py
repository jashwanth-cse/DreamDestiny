"""
TrainWatch Availability Load-Test Service — FastAPI Application.

Exposes:
  - GET  /health: Liveness and status probe
  - POST /run: Bounded load test runner (triggered by Cloud Scheduler / OIDC / API Key)
  - GET  /runs: Most recent test runs from Firestore
  - GET  /runs/{run_id}: Detailed run summary
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    Header,
    status,
    Depends,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.schemas import (
    RunRequest,
    RunSummary,
    HealthResponse,
    ScenarioType,
)
from app.services.load_generator import get_load_generator, LoadGeneratorService
from app.services.firestore_storage import get_firestore_storage, FirestoreStorageService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trainwatch.loadtest")

# State for preventing overlapping runs
_run_lock = asyncio.Lock()
_active_run_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Initializing TrainWatch Load-Test Service...")
    logger.info(f"Target Availability Endpoint: {settings.target_availability_url}")
    logger.info(f"GCP Project: '{settings.gcp_project_id}', Firestore Collection: '{settings.firestore_collection}'")
    yield
    logger.info("Shutting down TrainWatch Load-Test Service...")


app = FastAPI(
    title="TrainWatch Availability Load-Test Service",
    description="Standalone load-test service for Cloud Run and Cloud Scheduler.",
    version="1.0.0",
    lifespan=lifespan,
    # Mask docs in production Cloud Run environments (detected via K_SERVICE)
    docs_url=None if bool(settings.gcp_project_id and "K_SERVICE" in __import__("os").environ) else "/docs",
    redoc_url=None if bool(settings.gcp_project_id and "K_SERVICE" in __import__("os").environ) else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
):
    """
    Optional defense-in-depth authorization check.
    If SERVICE_API_KEY is configured in the environment, verifies either
    the X-API-Key header or Bearer token.
    (Note: Google Cloud Scheduler uses native IAM OIDC tokens validated by Cloud Run).
    """
    if not settings.service_api_key:
        return True

    expected = settings.service_api_key
    if x_api_key == expected:
        return True

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        if token == expected:
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid API key or OIDC token required.",
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check probe",
    tags=["Monitoring"],
)
async def health_check():
    """Liveness probe reporting Firestore connection and active test state."""
    storage = get_firestore_storage()
    return HealthResponse(
        status="healthy",
        service="trainwatch-loadtest-service",
        version="1.0.0",
        firestore_enabled=storage.is_connected,
        active_run=_run_lock.locked(),
    )


@app.post(
    "/run",
    response_model=RunSummary,
    summary="Execute load test run",
    description=(
        "Simulates concurrent train availability queries, audits deduplication, "
        "measures latency percentiles, and persists results to Firestore. "
        "Strictly prevents overlapping test runs with 409 Conflict."
    ),
    responses={
        200: {"description": "Load test completed successfully"},
        401: {"description": "Unauthorized access"},
        409: {"description": "A test run is already in progress"},
        504: {"description": "Test run exceeded deadline timeout"},
    },
    tags=["Execution"],
)
async def run_load_test(
    request: Optional[RunRequest] = None,
    auth_verified: bool = Depends(verify_auth),
    load_gen: LoadGeneratorService = Depends(get_load_generator),
    storage: FirestoreStorageService = Depends(get_firestore_storage),
):
    """Triggers a bounded load-test run and saves results to Firestore."""
    global _active_run_id

    # Fallback to default request if empty body posted
    run_req = request or RunRequest(
        scenario=ScenarioType(settings.default_scenario),
        concurrency=settings.default_concurrency,
        total_requests=settings.default_total_requests,
    )

    # 1. Non-blocking attempt to acquire concurrency lock
    if _run_lock.locked():
        logger.warning(f"Overlapping test run rejected. Current active run: {_active_run_id}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": "A load test run is currently in progress. Overlapping runs are rejected.",
                "active_run_id": _active_run_id,
            },
        )

    await _run_lock.acquire()
    try:
        _active_run_id = f"test_{asyncio.get_event_loop().time()}"

        # 2. Execute the load test with hard deadline timeout
        summary: RunSummary = await asyncio.wait_for(
            load_gen.execute_run(run_req),
            timeout=settings.run_deadline_seconds,
        )

        # 3. Persist run to Firestore
        persisted, doc_id = await storage.save_run(summary)
        summary.firestore_persisted = persisted
        summary.firestore_doc_id = doc_id

        return summary

    except asyncio.TimeoutError:
        logger.error(f"Load test exceeded deadline of {settings.run_deadline_seconds}s")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Test run exceeded maximum deadline of {settings.run_deadline_seconds} seconds.",
        )
    finally:
        _active_run_id = None
        _run_lock.release()


@app.get(
    "/runs",
    summary="List recent test runs",
    tags=["History"],
)
async def list_runs(
    limit: int = 10,
    storage: FirestoreStorageService = Depends(get_firestore_storage),
):
    """Retrieve recent test runs from Firestore (or local fallback)."""
    return await storage.get_recent_runs(limit=min(limit, 50))


@app.get(
    "/runs/{run_id}",
    summary="Get single test run by ID",
    tags=["History"],
)
async def get_run(
    run_id: str,
    storage: FirestoreStorageService = Depends(get_firestore_storage),
):
    """Retrieve a single test run by UUID."""
    run = await storage.get_run_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
