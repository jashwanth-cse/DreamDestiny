"""
Flight Service — FastAPI Microservice.
Provides flight search using SerpApi Google Flights API.
"""

import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.routes import flights
from app.exceptions import (
    FlightServiceError,
    AirportNotFoundError,
    InvalidFlightRequestError,
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderAPIError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Flight Transport Service API",
    description="Production-ready FastAPI microservice for searching flights using SerpApi Google Flights API.",
    version="1.0.0",
)

# ── CORS Middleware ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Timing and Logging Middleware ───────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info("Incoming Request: %s %s", request.method, request.url.path)

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    logger.info(
        "Completed Request: %s %s - Status: %d - Time: %.2fms",
        request.method, request.url.path, response.status_code, process_time
    )
    return response


# ── Exception Handlers ──────────────────────────────────────────────────────
@app.exception_handler(AirportNotFoundError)
async def airport_not_found_handler(request: Request, exc: AirportNotFoundError):
    logger.warning("Airport not found: %s", exc)
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": str(exc), "error_code": "AIRPORT_NOT_FOUND"}
    )


@app.exception_handler(InvalidFlightRequestError)
async def invalid_request_handler(request: Request, exc: InvalidFlightRequestError):
    logger.warning("Invalid flight request: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": str(exc), "error_code": "INVALID_REQUEST"}
    )


@app.exception_handler(ProviderAuthenticationError)
async def provider_auth_handler(request: Request, exc: ProviderAuthenticationError):
    logger.error("Provider authentication failure: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc), "error_code": "PROVIDER_AUTH_ERROR"}
    )


@app.exception_handler(ProviderTimeoutError)
async def provider_timeout_handler(request: Request, exc: ProviderTimeoutError):
    logger.error("Provider timeout: %s", exc)
    return JSONResponse(
        status_code=504,
        content={"success": False, "message": "Upstream flight provider timed out", "error_code": "PROVIDER_TIMEOUT"}
    )


@app.exception_handler(ProviderAPIError)
async def provider_api_handler(request: Request, exc: ProviderAPIError):
    logger.error("Provider API error: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"success": False, "message": str(exc), "error_code": "PROVIDER_API_ERROR"}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": "Invalid request payload", "error_code": "VALIDATION_ERROR"}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled Exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "error_code": "INTERNAL_ERROR"}
    )


# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(flights.router, tags=["Flights"])


# ── Health Check ────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "flight-service", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.flight_service_port, reload=True)
