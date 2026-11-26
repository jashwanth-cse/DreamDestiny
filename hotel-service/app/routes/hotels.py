"""
Hotels route — GET /hotels

Responsibilities:
  1. Validate query parameters
  2. Build the cache key
  3. Return cached result if available (cache HIT)
  4. Call SerpApi on a cache MISS, store result, then return
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.cache import get_cached, make_cache_key, set_cached
from app.models import GuestsModel, HotelsResponse, HotelModel
from app.services.serpapi_hotels import fetch_hotels

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/hotels",
    response_model=HotelsResponse,
    summary="Search hotels for a city and date range",
    responses={
        400: {"description": "Invalid date range or parameter values"},
        503: {"description": "SerpApi upstream error"},
    },
)
async def get_hotels(
    city: str = Query(
        ...,
        description="City to search hotels in.",
        min_length=1,
        examples=["Coimbatore"],
    ),
    check_in: str = Query(
        ...,
        description="Check-in date in YYYY-MM-DD format.",
        examples=["2026-08-20"],
    ),
    check_out: str = Query(
        ...,
        description="Check-out date in YYYY-MM-DD format.",
        examples=["2026-08-22"],
    ),
    adults: int = Query(
        default=2,
        ge=1,
        le=30,
        description="Number of adults (1–30).",
    ),
    children: int = Query(
        default=0,
        ge=0,
        le=10,
        description="Number of children (0–10).",
    ),
    fresh: bool = Query(default=False, description="Bypass the normal cache for Trip Rescue."),
):
    # ------------------------------------------------------------------
    # 1. Validate dates
    # ------------------------------------------------------------------
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Dates must be in YYYY-MM-DD format (e.g. 2026-08-20).",
        )

    if co <= ci:
        raise HTTPException(
            status_code=400,
            detail="check_out must be after check_in.",
        )

    if ci < date.today():
        raise HTTPException(
            status_code=400,
            detail="check_in cannot be in the past.",
        )

    # ------------------------------------------------------------------
    # 2. Cache lookup
    # ------------------------------------------------------------------
    cache_key = make_cache_key(city, check_in, check_out, adults, children)
    cached = None if fresh else get_cached(cache_key)

    if cached is not None:
        logger.info("Cache HIT  → %s", cache_key)
        return HotelsResponse(**cached)

    logger.info("Cache MISS → %s  — calling SerpApi", cache_key)

    # ------------------------------------------------------------------
    # 3. SerpApi call
    # ------------------------------------------------------------------
    try:
        raw_hotels = await fetch_hotels(
            city=city,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "SERPAPI_API_KEY is not set" in msg:
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=503, detail=msg)

    # ------------------------------------------------------------------
    # 4. Build response
    # ------------------------------------------------------------------
    hotels = [HotelModel(**h) for h in raw_hotels]

    response = HotelsResponse(
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=GuestsModel(adults=adults, children=children),
        count=len(hotels),
        hotels=hotels,
    )

    # ------------------------------------------------------------------
    # 5. Persist to cache (only on success)
    # ------------------------------------------------------------------
    set_cached(cache_key, response.model_dump())
    logger.info("Stored in cache → %s  (%d hotels)", cache_key, len(hotels))

    return response
