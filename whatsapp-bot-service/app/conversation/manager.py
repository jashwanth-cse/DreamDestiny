"""
Conversation Manager — orchestrates message lifecycle, session recovery,
concurrency locks, idempotency deduplication, and response dispatching.
"""

import logging
from typing import Optional

from app.schemas.webhook import NormalizedEvent, MessageType
from app.schemas.conversation import UserSession, ConversationState, MessageRecord, UserRecord
from app.storage.redis_store import redis_store
from app.storage.firestore_store import firestore_store
from app.understanding.message_parser import message_parser
from app.conversation.state_machine import StateMachine
from app.services.trip_service import trip_service
from app.whatsapp.client import whatsapp_client
from app.whatsapp.messages import build_text_message, build_button_message

logger = logging.getLogger(__name__)


class ConversationManager:
    async def process_incoming_event(self, event: NormalizedEvent):
        """
        End-to-end processing of a normalized incoming WhatsApp message.
        Guarantees idempotency, same-user race safety, and multi-user isolation.
        """
        wa_id = event.wa_id
        message_id = event.message_id

        # 1. Idempotency Check (Ignore duplicate webhook deliveries from Meta)
        if await redis_store.is_message_processed(message_id):
            logger.info("Ignoring already processed duplicate message %s for user %s", message_id, wa_id)
            return

        await redis_store.mark_message_processed(message_id)

        # 2. Acquire Distributed User Lock
        async with redis_store.user_lock(wa_id) as acquired:
            if not acquired:
                logger.warning("Could not acquire lock for user %s — another request in flight", wa_id)
                return

            # 3. Load or Recover Session (Redis hit -> continue; Redis miss -> Firestore recovery)
            session = await redis_store.get_session(wa_id)
            if not session:
                logger.info("Redis cache miss for user %s. Initiating recovery from Firestore.", wa_id)
                session = UserSession(wa_id=wa_id, user_name=event.user_name)
                # Check if returning user in Firestore
                user_rec = await firestore_store.get_user(wa_id)
                if user_rec:
                    session.user_name = user_rec.display_name
                else:
                    # First time user
                    await firestore_store.save_user(UserRecord(wa_id=wa_id, display_name=event.user_name))

            session.touch(message_id=message_id)

            # 4. Audit Log Inbound Message to Firestore
            await firestore_store.save_message(
                wa_id=wa_id,
                conversation_id=session.conversation_id,
                msg=MessageRecord(
                    message_id=message_id,
                    direction="inbound",
                    message_type=event.message_type.value,
                    text=event.text,
                    payload={"payload_id": event.payload_id},
                ),
            )

            # 5. Message Understanding (Deterministic + LLM fallback)
            slots = await message_parser.parse(event.text, event.payload_id)

            # 6. Advance State Machine
            new_state, response_payload = StateMachine.transition(session, slots)

            # 7. Persist Updated Session to Redis
            await redis_store.save_session(session)

            # 8. Send Response to User via WhatsApp Client
            body_text = response_payload.get("text", "")
            buttons = response_payload.get("buttons")

            if buttons:
                outgoing_payload = build_button_message(
                    recipient=wa_id,
                    body_text=body_text,
                    buttons=buttons,
                )
            else:
                outgoing_payload = build_text_message(recipient=wa_id, text=body_text)

            await whatsapp_client.send_message_payload(outgoing_payload)

            # Audit Log Outbound Message
            await firestore_store.save_message(
                wa_id=wa_id,
                conversation_id=session.conversation_id,
                msg=MessageRecord(
                    message_id=f"out_{message_id[:16]}",
                    direction="outbound",
                    message_type="interactive" if buttons else "text",
                    text=body_text,
                ),
            )

            # 9. If state transitioned to GENERATING, trigger background trip planning
            if new_state == ConversationState.GENERATING:
                logger.info("Triggering trip itinerary generation for user %s", wa_id)
                await trip_service.generate_trip_itinerary(session)


conversation_manager = ConversationManager()
