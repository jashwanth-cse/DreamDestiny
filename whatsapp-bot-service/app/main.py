"""
WhatsApp Bot Service — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.webhook import router as webhook_router
from app.storage.redis_store import redis_store
from app.storage.firestore_store import firestore_store
from app.whatsapp.client import whatsapp_client
from app.clients.planner_gateway import planner_gateway

# Setup structured logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("whatsapp-bot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing WhatsApp Bot Service in %s mode...", settings.app_env)
    await redis_store.connect()
    firestore_store.connect()
    yield
    # Shutdown
    logger.info("Shutting down WhatsApp Bot Service...")
    await redis_store.close()
    await whatsapp_client.close()
    await planner_gateway.close()


import os

is_production = (os.getenv("APP_ENV") or settings.app_env).lower() == "production"

app = FastAPI(
    title="Dream Destiny — WhatsApp Bot Service",
    description="Conversational WhatsApp interface for AI Travel Planning powered by Meta Cloud API.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# CORS
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

# Mount Routes
app.include_router(webhook_router, prefix="/whatsapp")
app.include_router(webhook_router)  # Direct /webhook mount


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — verifies the web server process is responsive."""
    return {"status": "ok", "service": "whatsapp-bot-service", "version": "1.0.0"}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe — verifies downstream dependencies and configs."""
    redis_ok = bool(redis_store._client is not None or redis_store._memory_cache is not None)
    return {
        "status": "ready",
        "redis_configured": redis_ok,
        "planner_gateway": settings.planner_gateway_url,
    }
