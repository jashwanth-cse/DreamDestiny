"""At-least-once processing for incoming WhatsApp events in Trip Rescue mode."""

import asyncio
import logging

from app.schemas.webhook import NormalizedEvent
from app.storage.redis_store import redis_store
from app.conversation.manager import conversation_manager

logger = logging.getLogger(__name__)


async def run_event_worker():
    while True:
        try:
            events = await redis_store.next_events()
            for stream_id, fields in events:
                payload = fields.get("payload", "")
                try:
                    event = NormalizedEvent.model_validate_json(payload)
                    await conversation_manager.process_incoming_event(event)
                    await redis_store.ack_event(stream_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Failed processing WhatsApp event %s", stream_id)
                    if await redis_store.dead_letter_if_exhausted(stream_id, payload, type(exc).__name__):
                        logger.error("Moved WhatsApp event %s to dead-letter stream", stream_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Incoming event worker error; retrying")
            await asyncio.sleep(2)
