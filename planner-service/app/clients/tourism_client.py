"""
Concrete Tourism client — calls the tourism-service.

GET {TOURISM_SERVICE_URL}/tourism?city=<city>&limit=<limit>

Response shape (from tourism-service/models.py):
    {
        "city": str,
        "count": int,
        "attractions": [
            {
                "name", "address", "rating", "review_count",
                "latitude", "longitude", "google_maps_url",
                "image_url", "types"
            }
        ]
    }
"""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.interfaces.tourism import TourismProvider
from app.schemas.context import AttractionContext

logger = logging.getLogger(__name__)


class TourismClient(TourismProvider):

    async def get_attractions(
        self,
        city: str,
        limit: int = 10,
    ) -> list[AttractionContext]:
        url = f"{settings.tourism_service_url}/tourism"
        params = {"city": city, "limit": limit}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, timeout=settings.http_timeout
                )
        except httpx.RequestError as exc:
            logger.warning("TourismClient network error: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "TourismClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return []

        try:
            data = response.json()
            return [AttractionContext(**a) for a in data.get("attractions", [])]
        except Exception as exc:
            logger.warning("TourismClient parse error: %s", exc)
            return []
