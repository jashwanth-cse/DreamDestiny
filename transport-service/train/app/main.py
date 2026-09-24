import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.routes import stations, trains, availability
from app.exceptions import StationNotFoundError, InvalidRequestError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the local railway station resolver once at startup."""
    from app.services.station_service import _ensure_resolver_loaded
    _ensure_resolver_loaded()
    yield
    # (no shutdown cleanup needed for the resolver)


app = FastAPI(
    title="Transport Service API",
    description="Production-ready FastAPI microservice for searching trains and stations.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Timing and Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Incoming Request: {request.method} {request.url}")
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = '{0:.2f}'.format(process_time)
    logger.info(f"Completed Request: {request.method} {request.url} - Status: {response.status_code} - Time: {formatted_process_time}ms")
    
    return response

# Exception Handlers
@app.exception_handler(StationNotFoundError)
async def station_not_found_exception_handler(request: Request, exc: StationNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": "Station not found"}
    )

@app.exception_handler(InvalidRequestError)
async def invalid_request_exception_handler(request: Request, exc: InvalidRequestError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": "Invalid request"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": "Invalid request"}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"}
    )

# Routers
app.include_router(stations.router, prefix="/api/v1/stations", tags=["Stations"])
app.include_router(trains.router, prefix="/api/v1/trains", tags=["Trains"])
app.include_router(availability.router, prefix="/api/v1/trains/availability", tags=["Availability"])

# Health Check
@app.get("/health")
def health_check():
    return {"status": "healthy"}
