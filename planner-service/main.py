"""
Planner Service — FastAPI application.

Run with:
    uvicorn main:app --reload --port 8000

Health:  GET  http://localhost:8000/health
Plan:    POST http://localhost:8000/plan/context
Swagger: http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes.planner import router as planner_router
from app.api.routes.plan import router as plan_router

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── App ───────────────────────────────────────────────────────────────────────

import os

is_production = os.getenv("APP_ENV", "").lower() == "production"

app = FastAPI(
    title="Dream Destiny — Planner Service",
    description=(
        "Orchestrates Tourism, Transport, Hotel, and Route services to "
        "build a unified TripContext, then runs the Gemini Planning Agent "
        "to produce a structured day-by-day Itinerary.\n\n"
        "**POST /plan/context** — data only (no LLM)\n"
        "**POST /plan** — full AI itinerary"
    ),
    version="2.0.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

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

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(planner_router)
app.include_router(plan_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe."""
    return {"status": "ok", "service": "planner-service", "version": "2.0.0"}
