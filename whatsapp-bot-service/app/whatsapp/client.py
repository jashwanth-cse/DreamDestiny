"""
Async HTTP client for interacting with the Meta WhatsApp Cloud API.
Sends messages, handles retries, and supports test-mode simulation.
"""

import logging
from typing import Dict, Any, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(
        self,
        phone_number_id: str = settings.whatsapp_phone_number_id,
        access_token: str = settings.whatsapp_access_token,
        api_version: str = settings.whatsapp_api_version,
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}/{phone_number_id}"
        self._sent_messages_log: List[Dict[str, Any]] = []  # For tests / mock simulation
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        import asyncio
        if self._client is not None:
            try:
                loop = asyncio.get_running_loop()
                if getattr(self._client, "_loop", None) is not None and self._client._loop != loop:
                    await self._client.aclose()
                    self._client = None
            except Exception:
                self._client = None

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def send_message_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Sends an arbitrary message payload to the WhatsApp Cloud API.
        If access token is missing or in test environment, logs and records the message.
        Automatically chunks text messages > 4096 characters.
        """
        recipient = payload.get("to", "unknown")
        msg_type = payload.get("type", "unknown")

        self._sent_messages_log.append(payload)

        # Handle message chunking for long text messages (>4096 chars)
        if msg_type == "text" and "text" in payload and "body" in payload["text"]:
            body = payload["text"]["body"]
            if len(body) > 4000:
                logger.info("Message exceeds WhatsApp length limit. Chunking...")
                success = True
                chunks = [body[i:i+4000] for i in range(0, len(body), 4000)]
                for i, chunk in enumerate(chunks):
                    chunk_payload = {**payload, "text": {"body": chunk, "preview_url": False}}
                    if not await self._send_single_payload(chunk_payload, recipient):
                        success = False
                return success

        return await self._send_single_payload(payload, recipient)

    async def _send_single_payload(self, payload: Dict[str, Any], recipient: str) -> bool:
        if settings.app_env == "test" or not self.access_token or not self.phone_number_id:
            logger.info(
                "[MOCK WHATSAPP] Outgoing to %s (type=%s): %s",
                recipient,
                payload.get("type", "unknown"),
                payload.get("text", {}).get("body") or payload.get("interactive", {}).get("body", {}).get("text", ""),
            )
            return True

        url = f"{self.base_url}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        client = await self.get_client()
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.info("Successfully sent WhatsApp message to %s [status=%d]", recipient, resp.status_code)
                return True
            else:
                logger.error("Meta WhatsApp API error: %d - %s", resp.status_code, resp.text)
                return False
        except Exception as e:
            logger.error("Failed to connect to Meta WhatsApp Cloud API: %s", e)
            return False

    def get_sent_messages(self) -> List[Dict[str, Any]]:
        """Used in test suites to verify outgoing messages."""
        return list(self._sent_messages_log)

    def clear_sent_messages(self):
        self._sent_messages_log.clear()


whatsapp_client = WhatsAppClient()
