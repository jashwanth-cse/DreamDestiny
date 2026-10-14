"""
Hotel Service — FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --port 8002

Swagger UI: http://localhost:8002/docs
Health:     GET http://localhost:8002/health
Hotels:     GET http://localhost:8002/hotels?city=Coimbatore&check_in=2026-08-20&check_out=2026-08-22
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.hotels import router as hotels_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ---------------------------------------------------------------------------
import os

is_production = os.getenv("APP_ENV", "").lower() == "production"

app = FastAPI(
    title="Dream Destiny — Hotel Service",
    description=(
        "Returns normalized hotel listings for a given city and date range "
        "using the SerpApi Google Hotels engine."
    ),
    version="1.0.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

frontend_origin = os.getenv("FRONTEND_ORIGIN", settings.frontend_origin)

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

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(hotels_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe."""
    return {"status": "ok"}
