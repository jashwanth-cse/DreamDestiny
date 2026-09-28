"""
Meta WhatsApp Cloud API Webhook Endpoints.
GET /webhook — Verification handshake
POST /webhook — Real-time event receiver
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, Response, BackgroundTasks, Query, status

from app.schemas.webhook import WebhookPayload, NormalizedEvent
from app.conversation.manager import conversation_manager
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Webhook"])


@router.get("/webhook")
@router.get("/webhooks/whatsapp")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """
    Verification challenge handshake for Meta WhatsApp Cloud API configuration.
    """
    logger.info("Received WhatsApp Webhook Verification probe: mode=%s", hub_mode)

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("Webhook verification successful! Responding with challenge.")
        return Response(content=hub_challenge or "", media_type="text/plain")

    logger.warning("Webhook verification failed: Invalid verify token or mode.")
    return Response(content="Verification failed", status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhook")
@router.post("/webhooks/whatsapp")
async def receive_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
):
    """
    Receives incoming WhatsApp events (messages, button clicks, status updates).
    Quickly returns HTTP 200 OK to acknowledge Meta, dispatching processing in background.
    """
    for entry in payload.entry:
        for change in entry.changes:
            val = change.value
            if not val.messages:
                continue

            contacts = val.contacts or []
            contact_map = {c.wa_id: c for c in contacts}

            for msg in val.messages:
                contact = contact_map.get(msg.from_)
                event = NormalizedEvent.from_raw_message(msg, contact)
                logger.info(
                    "Received incoming WhatsApp message [id=%s, type=%s, from=%s]",
                    event.message_id,
                    event.message_type.value,
                    event.wa_id,
                )
                # Dispatch processing without blocking webhook acknowledgment
                background_tasks.add_task(conversation_manager.process_incoming_event, event)

    return {"status": "received"}
