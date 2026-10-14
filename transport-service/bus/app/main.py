"""
Bus Service — FastAPI Application Entry Point

Mirrors the architecture and coding style of the existing Train service.
"""

import sys
import os
import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

# Make the provider importable when running from the bus/ directory
sys.path.insert(0, os.path.dirname(__file__))

from app.routes import buses
from app.exceptions import (
    BusServiceError,
    BusProviderUnavailableError,
    BusSearchError,
    BusNoResultsError,
    CityNotFoundError,
    InvalidCityRouteError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

is_production = os.getenv("APP_ENV", "").lower() == "production"

app = FastAPI(
    title="Bus Service API",
    description=(
        "Production-ready FastAPI microservice for searching buses. "
        "Powered by the RedBus provider via curl_cffi Chrome impersonation."
    ),
    version="1.0.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
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

# ── Request Timing & Logging Middleware ───────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Incoming Request: {request.method} {request.url}")

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"Completed Request: {request.method} {request.url} "
        f"- Status: {response.status_code} "
        f"- Time: {process_time:.2f}ms"
    )
    return response

# ── Exception Handlers ────────────────────────────────────────────────────────
@app.exception_handler(CityNotFoundError)
async def city_not_found_handler(request: Request, exc: CityNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": str(exc)},
    )

@app.exception_handler(InvalidCityRouteError)
async def invalid_city_route_handler(request: Request, exc: InvalidCityRouteError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": str(exc)},
    )

@app.exception_handler(BusNoResultsError)
async def no_results_handler(request: Request, exc: BusNoResultsError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": str(exc)},
    )

@app.exception_handler(BusProviderUnavailableError)
async def provider_unavailable_handler(request: Request, exc: BusProviderUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"success": False, "message": "Bus provider is currently unavailable. Please try again."},
    )

@app.exception_handler(BusSearchError)
async def search_error_handler(request: Request, exc: BusSearchError):
    logger.error(f"Bus search error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "An error occurred while searching for buses."},
    )

@app.exception_handler(BusServiceError)
async def service_error_handler(request: Request, exc: BusServiceError):
    logger.error(f"Bus service error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal service error."},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": "Invalid request parameters."},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error."},
    )

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(buses.router, prefix="/api/v1/buses", tags=["Buses"])

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check():
    """Returns the current health status of the bus service."""
    return {"status": "healthy", "service": "bus-service", "version": "1.0.0"}
