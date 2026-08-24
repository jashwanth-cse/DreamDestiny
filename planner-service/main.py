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

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dream Destiny — Planner Service",
    description=(
        "Orchestrates Tourism, Transport, Hotel, and Route services to "
        "build a unified TripContext. Pure coordination — no LLM, no business logic."
    ),
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(planner_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe."""
    return {"status": "ok", "service": "planner-service"}
