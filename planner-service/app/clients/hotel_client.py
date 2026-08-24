"""
Concrete Hotel client — calls the hotel-service.

GET {HOTEL_SERVICE_URL}/hotels?city=<city>&check_in=<date>&check_out=<date>&adults=<n>&children=<n>

Response shape (from hotel-service/app/models.py):
    {
        "city", "check_in", "check_out",
        "guests": {"adults", "children"},
        "count": int,
        "hotels": [
            {
                "id", "name", "description",
                "latitude", "longitude",
                "rating", "review_count", "hotel_class",
                "price": {"per_night", "total", "currency"},
                "check_in_time", "check_out_time",
                "amenities", "image_url", "website_url", "nearby_places"
            }
        ]
    }
"""

import logging

import httpx

from app.config import settings
from app.interfaces.hotel import HotelProvider
from app.schemas.context import HotelContext, HotelPriceContext

logger = logging.getLogger(__name__)


class HotelClient(HotelProvider):

    async def get_hotels(
        self,
        city: str,
        check_in: str,
        check_out: str,
        adults: int,
        children: int = 0,
    ) -> list[HotelContext]:
        url = f"{settings.hotel_service_url}/hotels"
        params = {
            "city": city,
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "children": children,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, timeout=settings.http_timeout
                )
        except httpx.RequestError as exc:
            logger.warning("HotelClient network error: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "HotelClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return []

        try:
            data = response.json()
            result = []
            for h in data.get("hotels", []):
                price_raw = h.pop("price", {}) or {}
                hotel = HotelContext(
                    **h,
                    price=HotelPriceContext(**price_raw),
                )
                result.append(hotel)
            return result
        except Exception as exc:
            logger.warning("HotelClient parse error: %s", exc)
            return []
