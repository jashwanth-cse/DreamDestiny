"""
Concrete Route client — calls the route-service.

GET {ROUTE_SERVICE_URL}/route?origin=<origin>&destination=<destination>

Response shape (from route-service/app/models.py):
    {
        "origin": str,
        "destination": str,
        "distance_km": float | null,
        "routes": [
            {"mode": str, "duration_minutes": int | null}
        ]
    }
"""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.interfaces.route import RouteProvider
from app.schemas.context import RouteContext, RouteModeContext

logger = logging.getLogger(__name__)


class RouteClient(RouteProvider):

    async def get_route(
        self,
        origin: str,
        destination: str,
    ) -> Optional[RouteContext]:
        url = f"{settings.route_service_url}/route"
        params = {"origin": origin, "destination": destination}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, params=params, timeout=settings.http_timeout
                )
        except httpx.RequestError as exc:
            logger.warning("RouteClient network error: %s", exc)
            return None

        if response.status_code != 200:
            logger.warning(
                "RouteClient returned %d: %s",
                response.status_code, response.text[:200],
            )
            return None

        try:
            data = response.json()
            return RouteContext(
                origin=data["origin"],
                destination=data["destination"],
                distance_km=data.get("distance_km"),
                routes=[
                    RouteModeContext(**m) for m in data.get("routes", [])
                ],
            )
        except Exception as exc:
            logger.warning("RouteClient parse error: %s", exc)
            return None
