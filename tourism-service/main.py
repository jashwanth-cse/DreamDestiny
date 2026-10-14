"""
Tourism Service — FastAPI application entry point.

Run with:
    uvicorn main:app --reload --port 8001
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from models import Attraction, TourismResponse
from services.google_places import fetch_tourist_attractions

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

# Load .env before anything else so GOOGLE_MAPS_API_KEY is available
load_dotenv()

is_production = os.getenv("APP_ENV", "").lower() == "production"

app = FastAPI(
    title="Dream Destiny — Tourism Service",
    description=(
        "Returns tourist attractions for a given city "
        "using the Google Places API (New)."
    ),
    version="1.0.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — returns 200 OK when the service is running."""
    return {"status": "ok"}


@app.get(
    "/tourism",
    response_model=TourismResponse,
    tags=["Tourism"],
    summary="Get tourist attractions for a city",
    responses={
        400: {"description": "Bad request — missing or invalid parameters"},
        503: {"description": "Google Places API unreachable or returned an error"},
    },
)
async def get_tourism(
    city: str = Query(
        ...,
        description="City name to search tourist attractions for.",
        min_length=1,
        examples=["Coimbatore"],
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of attractions to return (1–20).",
    ),
):
    """
    Fetch tourist attractions for *city* from the Google Places API
    and return them in a clean JSON envelope.

    - **city**: required — e.g. `Coimbatore`, `Paris`, `Tokyo`
    - **limit**: optional — defaults to `10`, max `20`
    """
    try:
        raw_attractions = await fetch_tourist_attractions(
            city_name=city,
            max_results=limit,
        )
    except RuntimeError as exc:
        # Distinguish between a missing API key (bad config) and a
        # downstream Google API failure.
        msg = str(exc)
        if "GOOGLE_MAPS_API_KEY is not set" in msg:
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=503, detail=msg)

    attractions = [Attraction(**a) for a in raw_attractions]

    return TourismResponse(
        city=city,
        count=len(attractions),
        attractions=attractions,
    )
