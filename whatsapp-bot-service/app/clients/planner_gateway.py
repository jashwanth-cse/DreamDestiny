"""
HTTP client for communicating with the existing Planner Gateway / NGINX reverse proxy.
Adheres strictly to Section 17 of the production specification:
- Reuses the existing backend planning pipeline.
- Propagates correlation IDs for end-to-end tracing.
- Implements connection pooling, explicit timeouts, and structured error handling.
"""

import logging
from typing import Dict, Any, Optional
import httpx

from app.schemas.trip import TripRequest
from app.config import settings

logger = logging.getLogger(__name__)


class PlannerGatewayError(Exception):
    """Raised when the backend planner service returns an error or is unreachable."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class PlannerGatewayClient:
    def __init__(self, base_url: str = settings.planner_gateway_url, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate_itinerary(
        self, trip_request: TripRequest, correlation_id: str
    ) -> Dict[str, Any]:
        """
        Calls POST /plan on the backend planner gateway with the validated TripRequest.
        """
        client = await self.get_client()
        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        payload = trip_request.model_dump(mode="json")
        logger.info(
            "Calling Planner Gateway POST /plan [correlation_id=%s] for %s -> %s (%s to %s)",
            correlation_id,
            trip_request.origin,
            trip_request.destination,
            trip_request.start_date,
            trip_request.end_date,
        )

        try:
            resp = await client.post("/plan", json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info("Planner Gateway returned 200 OK [correlation_id=%s]", correlation_id)
                return resp.json()
            else:
                err_msg = f"Planner returned HTTP {resp.status_code}: {resp.text}"
                logger.error("Planner error [correlation_id=%s]: %s", correlation_id, err_msg)
                raise PlannerGatewayError(err_msg, status_code=resp.status_code)
        except httpx.TimeoutException as exc:
            logger.error("Planner Gateway timed out after %ss [correlation_id=%s]", self.timeout, correlation_id)
            raise PlannerGatewayError("The travel planner took too long to generate your itinerary.", status_code=504) from exc
        except httpx.RequestError as exc:
            logger.error("Network error contacting Planner Gateway [correlation_id=%s]: %s", correlation_id, exc)
            raise PlannerGatewayError("Could not connect to the backend planning service.", status_code=503) from exc

    async def check_transport(
        self, trip_request: TripRequest, correlation_id: str
    ) -> Dict[str, Any]:
        """
        Calls POST /check-transport on the backend planner gateway.
        """
        client = await self.get_client()
        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        payload = trip_request.model_dump(mode="json")
        try:
            resp = await client.post("/check-transport", json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error("Planner /check-transport error: %s", resp.text)
                return {"status": "ERROR"}
        except Exception as exc:
            logger.error("Planner /check-transport failed: %s", exc)
            return {"status": "ERROR"}

planner_gateway = PlannerGatewayClient()
