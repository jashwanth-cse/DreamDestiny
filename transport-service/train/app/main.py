import os
import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.routes import stations, trains, availability, schedule
from app.exceptions import (
    StationNotFoundError,
    InvalidRequestError,
    TrainNotFoundError,
    UpstreamTimeoutError,
    UpstreamConnectionError,
    UpstreamServiceError,
    CircuitBreakerOpenError,
)
from app.services.availability_service import get_availability_service
from app.services.schedule_service import get_schedule_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Service lifespan manager:
    - Warms the local railway station dataset index once at startup
    - Gracefully closes HTTP client connection pools on shutdown
    """
    from app.services.station_service import _ensure_resolver_loaded
    logger.info("Initializing station resolver dataset index...")
    _ensure_resolver_loaded()
    logger.info("Station resolver dataset loaded.")
    yield
    logger.info("Shutting down Transport Service, releasing HTTP resources...")
    avl_service = get_availability_service()
    await avl_service.aclose()
    sched_service = get_schedule_service()
    await sched_service.aclose()
    logger.info("Transport Service shutdown complete.")


# Environment & Production Detection
is_cloud_run = bool(os.getenv("K_SERVICE"))
app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production" if is_cloud_run else "development")).lower()
is_production = app_env in ("production", "prod") or is_cloud_run
enable_docs = os.getenv("ENABLE_DOCS", "true").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Transport Service API",
    description="Production-ready FastAPI microservice for searching trains, stations, schedules, and live seat availability.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if enable_docs else None,
    redoc_url="/redoc" if enable_docs else None,
    openapi_url="/openapi.json" if enable_docs else None,
)

# CORS Middleware
frontend_origin = os.getenv("FRONTEND_ORIGIN", "https://dreamdestiny.duckdns.org")

if is_production:
    allowed_origins = [o.strip() for o in frontend_origin.split(",") if o.strip()]
    allow_credentials = True
else:
    allowed_origins = [frontend_origin] if frontend_origin != "*" else ["*"]
    allow_credentials = False if "*" in allowed_origins else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Timing, Correlation ID, and Structured Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    correlation_id = (
        request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Request-ID")
        or uuid.uuid4().hex[:12]
    )
    request.state.correlation_id = correlation_id

    start_time = time.monotonic()
    logger.info(f"[corr_id={correlation_id}] Incoming: {request.method} {request.url.path}")

    response = await call_next(request)

    process_time_ms = (time.monotonic() - start_time) * 1000
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        f"[corr_id={correlation_id}] Completed: {request.method} {request.url.path} "
        f"- Status: {response.status_code} - Time: {process_time_ms:.2f}ms"
    )

    return response


# Exception Handlers
@app.exception_handler(StationNotFoundError)
async def station_not_found_exception_handler(request: Request, exc: StationNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": "Station not found"}
    )


@app.exception_handler(TrainNotFoundError)
async def train_not_found_exception_handler(request: Request, exc: TrainNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": str(exc) or "Train not found"}
    )


@app.exception_handler(InvalidRequestError)
async def invalid_request_exception_handler(request: Request, exc: InvalidRequestError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": str(exc) or "Invalid request"}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    detail = "Invalid request parameters"
    if errors:
        first_err = errors[0]
        msg = first_err.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        loc = " -> ".join(str(l) for l in first_err.get("loc", []) if l != "body")
        detail = f"{loc}: {msg}" if loc else msg

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "message": detail,
            "errors": [e.get("msg", "") for e in errors],
        }
    )


@app.exception_handler(UpstreamTimeoutError)
async def upstream_timeout_handler(request: Request, exc: UpstreamTimeoutError):
    return JSONResponse(
        status_code=504,
        content={"success": False, "message": "Upstream schedule or availability provider timed out."}
    )


@app.exception_handler(CircuitBreakerOpenError)
async def circuit_breaker_handler(request: Request, exc: CircuitBreakerOpenError):
    return JSONResponse(
        status_code=503,
        content={"success": False, "message": "Service is temporarily unavailable due to upstream outage."}
    )


@app.exception_handler(UpstreamConnectionError)
@app.exception_handler(UpstreamServiceError)
async def upstream_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=502,
        content={"success": False, "message": "Upstream service error."}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    corr_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(f"[corr_id={corr_id}] Unhandled Exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"}
    )


# Routers
app.include_router(stations.router, prefix="/api/v1/stations", tags=["Stations"])
app.include_router(trains.router, prefix="/api/v1/trains", tags=["Trains"])
app.include_router(availability.router, prefix="/api/v1/trains/availability", tags=["Availability"])
app.include_router(schedule.router, prefix="/api/v1/trains", tags=["Schedule"])


# Health & Readiness Probes
@app.get("/health", summary="Liveness Probe", tags=["System"])
def health_check():
    """
    Sub-millisecond liveness probe with zero external dependencies.
    """
    return {"status": "healthy", "service": "dream-destiny-train", "version": "2.0.0"}


@app.get("/ready", summary="Readiness Probe", tags=["System"])
def readiness_check():
    """
    Readiness probe verifying that local dataset index is loaded and operational.
    """
    from app.services.station_service import _resolver, _ensure_resolver_loaded
    _ensure_resolver_loaded()
    is_ready = getattr(_resolver, "_loaded", False)
    if not is_ready:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "Station dataset loading"})
    total = getattr(_resolver, "total_stations", 0)
    return {"status": "ready", "service": "dream-destiny-train", "total_stations": total}
