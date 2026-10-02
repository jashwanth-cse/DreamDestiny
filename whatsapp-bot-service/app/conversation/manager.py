"""
Conversation Manager — orchestrates message lifecycle, session recovery,
concurrency locks, idempotency deduplication, guardrail shield, and response dispatching.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.schemas.webhook import NormalizedEvent, MessageType
from app.schemas.conversation import UserSession, ConversationState, MessageRecord, UserRecord
from app.storage.redis_store import redis_store
from app.storage.firestore_store import firestore_store
from app.understanding.message_parser import message_parser
from app.understanding.guardrail import guardrail_shield
from app.conversation.state_machine import StateMachine
from app.conversation import prompts
from app.services.trip_service import trip_service
from app.whatsapp.client import whatsapp_client
from app.whatsapp.messages import build_text_message, build_button_message, format_itinerary_message

logger = logging.getLogger(__name__)

GREETINGS = {"hi", "hello", "hey", "hola", "namaste", "vanakkam", "good morning", "good evening"}


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

        # 2. Strict Domain Guardrail Shield Check
        # If user queries off-topic matters (coding, math, politics, trivia), strictly do not respond
        is_in_scope = await guardrail_shield.is_in_scope(event.text, event.payload_id)
        if not is_in_scope:
            logger.warning("[GUARDRAIL] Dropped off-topic input for user %s: '%s'", wa_id, event.text)
            return

        # 3. Acquire Distributed User Lock
        async with redis_store.user_lock(wa_id) as acquired:
            if not acquired:
                logger.warning("Could not acquire lock for user %s — another request in flight", wa_id)
                return

            # 4. Load or Recover Session (Redis hit -> continue; Redis miss -> Firestore recovery)
            session = await redis_store.get_session(wa_id)
            is_new_session = False
            if not session:
                logger.info("Redis cache miss for user %s. Initiating recovery from Firestore.", wa_id)
                session = UserSession(wa_id=wa_id, user_name=event.user_name)
                is_new_session = True
                user_rec = await firestore_store.get_user(wa_id)
                if user_rec:
                    session.user_name = user_rec.display_name
                else:
                    await firestore_store.save_user(UserRecord(wa_id=wa_id, display_name=event.user_name))

            # Check for Inactivity Pause (e.g. > 2 hours) or returning to Completed Trip
            is_inactive_return = False
            if not is_new_session and session.last_activity:
                try:
                    last_dt = datetime.fromisoformat(session.last_activity.replace("Z", "+00:00"))
                    seconds_idle = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if seconds_idle > 7200:  # 2 hours
                        is_inactive_return = True
                except Exception:
                    pass

            session.touch(message_id=message_id)

            # 5. Audit Log Inbound Message to Firestore
            await firestore_store.save_message(
                wa_id=wa_id,
                conversation_id=session.conversation_id,
                msg=MessageRecord(
                    message_id=message_id,
                    direction="inbound",
                    message_type=event.message_type.value,
                    text=event.text,
                    payload={"payload_id": event.payload_id},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
            )

            # 6. Message Understanding (Deterministic + Context-Aware + LLM fallback)
            slots = await message_parser.parse(
                text=event.text,
                payload_id=event.payload_id,
                current_state=session.state,
                current_draft=session.draft,
            )

            response_payload = None
            new_state = session.state

            clean_text = event.text.strip().lower() if event.text else ""

            # 7. Inactivity / Resumption Interceptor
            # If user returns after long inactivity OR previous itinerary was already finalized,
            # and sends a casual greeting without specific trip slots:
            if (
                (is_inactive_return or session.state == ConversationState.COMPLETED)
                and clean_text in GREETINGS
                and not slots.destination
                and not slots.origin
                and not slots.modification_intent
                and not slots.menu_intent
                and not slots.past_trips_intent
            ):
                session.paused_state = session.state
                session.state = ConversationState.RESUME_CHOICE
                is_comp = (session.paused_state == ConversationState.COMPLETED)
                response_payload = prompts.get_resumption_prompt(
                    session.user_name, session.draft, is_completed=is_comp
                )
                new_state = ConversationState.RESUME_CHOICE

            # 8. Saved Past Trips Handling
            elif slots.past_trips_intent:
                session.state = ConversationState.VIEWING_TRIPS
                past_trips = await redis_store.get_user_trips(wa_id, limit=5)
                response_payload = prompts.get_past_trips_prompt(past_trips)
                new_state = ConversationState.VIEWING_TRIPS

            elif session.state == ConversationState.VIEWING_TRIPS and slots.selected_trip_number:
                idx = slots.selected_trip_number - 1
                trip_data = await redis_store.get_user_trip_by_index(wa_id, idx)
                if trip_data and "itinerary_data" in trip_data:
                    session.state = ConversationState.COMPLETED
                    itinerary_text = format_itinerary_message(
                        trip_data["itinerary_data"],
                        origin=trip_data.get("origin", "Origin"),
                        destination=trip_data.get("destination", "Destination"),
                    )
                    response_payload = {"text": itinerary_text}
                    new_state = ConversationState.COMPLETED
                else:
                    response_payload = {
                        "text": "Could not find that saved trip. Reply _'Past trips'_ to see your saved itineraries."
                    }

            # 9. Standard State Machine Advance
            if response_payload is None:
                old_state = session.state
                new_state, response_payload = StateMachine.transition(session, slots)

                # Waitlist/RAC Intercept
                if (
                    old_state == ConversationState.COLLECT_TRAIN_CLASS
                    and slots.train_class
                    and session.draft.is_complete_for_planning()
                    and new_state != ConversationState.CONFIRM_CITY_TYPO
                ):
                    # Pause transition, query planner-service fast check
                    logger.info("Checking transport availability for user %s", wa_id)
                    
                    status_dict = await trip_service.check_transport_availability(session.draft, session.correlation_id)
                    status = status_dict.get("status")
                    
                    if status in ("RAC", "WL"):
                        session.state = ConversationState.HANDLE_WAITLIST_RAC
                        new_state = ConversationState.HANDLE_WAITLIST_RAC
                        
                        prompt_text = ""
                        if status == "RAC":
                            prompt_text = "⚠️ *Berth is not available, only RAC seats available.*\n\nProceed or change?"
                        else:
                            prompt_text = "⚠️ *Only Waitlist (WL) seats are available for this train class.*\n\nShall I proceed with alternate transport, or alternate date?"
                            
                        response_payload = {
                            "text": prompt_text,
                            "buttons": [
                                ("btn_wl_proceed", "✅ Proceed Anyway"),
                                ("btn_wl_change", "🔄 Change Transport"),
                            ]
                        }
                    # If AVL or NOT_FOUND, just continue to the next state normally

            # 10. Persist Updated Session to Redis
            await redis_store.save_session(session)

            # 11. Send Response to User via WhatsApp Client
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
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
            )

            # 12. If state transitioned to GENERATING, trigger background trip planning
            if new_state == ConversationState.GENERATING:
                logger.info("Triggering trip itinerary generation for user %s", wa_id)
                await trip_service.generate_trip_itinerary(session)


conversation_manager = ConversationManager()
