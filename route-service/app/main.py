"""
Route Service — FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --port 8003

Health:  GET http://localhost:8003/health
Route:   GET http://localhost:8003/route?origin=Chennai&destination=Coimbatore
Swagger: http://localhost:8003/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.route import router as route_router

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
    title="Dream Destiny — Route Service",
    description=(
        "Returns verified driving and transit routes between two locations "
        "using the Google Routes API. Never invents distance or duration."
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

app.include_router(route_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe."""
    return {"status": "ok"}
