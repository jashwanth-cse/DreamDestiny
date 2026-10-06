"""
Service responsible for coordinating trip generation, calling the backend planner gateway,
persisting versioned itineraries in Firestore, and returning formatted WhatsApp responses.
"""

import logging
import asyncio
from typing import Dict, Any, Optional

from app.schemas.conversation import UserSession, ConversationState, TripRecord, ItineraryVersionRecord
from app.schemas.trip import TripRequest
from app.clients.planner_gateway import planner_gateway, PlannerGatewayError
from app.storage.firestore_store import firestore_store
from app.storage.redis_store import redis_store
from app.whatsapp.client import whatsapp_client
from app.whatsapp.messages import format_itinerary_message, build_text_message, build_review_list_message

logger = logging.getLogger(__name__)


class TripService:
    @staticmethod
    async def check_transport_availability(draft: TripRequest, correlation_id: str) -> dict:
        """Call Planner Gateway fast check."""
        try:
            req = draft.to_trip_request()
            return await planner_gateway.check_transport(req, correlation_id)
        except Exception as e:
            logger.error("Failed to check transport: %s", e)
            return {"status": "ERROR"}

    @staticmethod
    async def generate_trip_itinerary(session: UserSession) -> bool:
        """
        Builds TripRequest from active session draft, calls existing Planner Gateway,
        persists records in Firestore, and sends formatted itinerary to the user.
        """
        correlation_id = session.correlation_id
        wa_id = session.wa_id

        try:
            trip_request = session.draft.to_trip_request()
        except ValueError as err:
            logger.error("Cannot build TripRequest for %s: %s", wa_id, err)
            await whatsapp_client.send_message_payload(
                build_text_message(wa_id, "⚠️ Some trip details were missing. Let's start over by typing _'New trip'_.")
            )
            session.state = ConversationState.START
            await redis_store.save_session(session)
            return False

        try:
            # Check global active generations
            active_gen = await redis_store.get_active_generations()
            if active_gen >= 2:
                logger.info(f"High traffic (active={active_gen}), queueing {wa_id}")
                await whatsapp_client.send_message_payload(
                    build_text_message(wa_id, "🌴 *High Traffic Alert!* 🌴\nWe are currently experiencing a high volume of travel requests. Your itinerary is safely in the queue and will be generated shortly. Thanks for your patience! ✨")
                )
            
            # Wait for a slot
            while True:
                acquired = await redis_store.acquire_generation_slot(limit=2)
                if acquired:
                    break
                await asyncio.sleep(3)

            try:
                # 1. Call Backend Planner Gateway
                itinerary_data = await planner_gateway.generate_itinerary(trip_request, correlation_id)
            finally:
                await redis_store.release_generation_slot()

            # 2. Persist Trip & Itinerary in Firestore
            trip = TripRecord(
                wa_id=wa_id,
                conversation_id=session.conversation_id,
                origin=trip_request.origin,
                destination=trip_request.destination,
                start_date=trip_request.start_date.isoformat(),
                end_date=trip_request.end_date.isoformat(),
                travelers=trip_request.travelers,
                latest_version=1,
                trip_request_data=trip_request.model_dump(mode="json"),
            )
            await firestore_store.save_trip(trip)

            version = ItineraryVersionRecord(
                version_number=1,
                itinerary_data=itinerary_data,
                modification_prompt=None,
                is_current=True,
            )
            await firestore_store.save_itinerary_version(wa_id, trip.trip_id, version)

            # 3. Update active session and archive in Redis
            session.current_trip_id = trip.trip_id
            session.state = ConversationState.AWAITING_REVIEW
            await redis_store.save_session(session)

            # Archive trip into Redis for fast My Trips / Menu access
            trip_duration = session.draft.duration_days or max(1, (trip_request.end_date - trip_request.start_date).days)
            budget_str = str(session.draft.budget_level.value if session.draft.budget_level else "medium")
            archived_trip = {
                "trip_id": trip.trip_id,
                "origin": trip_request.origin,
                "destination": trip_request.destination,
                "days": trip_duration,
                "travelers": trip_request.travelers,
                "budget_level": budget_str,
                "created_at": trip.created_at,
                "itinerary_data": itinerary_data,
            }
            await redis_store.save_user_trip(wa_id, archived_trip)

            # 4. Format and Send Itinerary to WhatsApp
            formatted_text = format_itinerary_message(
                itinerary_data, origin=trip_request.origin, destination=trip_request.destination
            )
            await whatsapp_client.send_message_payload(build_text_message(wa_id, formatted_text))

            # 5. Send Interactive 5-Star Rating Prompt
            review_msg = build_review_list_message(wa_id, destination=trip_request.destination)
            await whatsapp_client.send_message_payload(review_msg)
            return True

        except PlannerGatewayError as exc:
            logger.error("Planner Gateway failed for %s: %s", wa_id, exc)
            session.state = ConversationState.CONFIRM_TRIP  # allow retry
            await redis_store.save_session(session)
            await whatsapp_client.send_message_payload(
                build_text_message(
                    wa_id,
                    "⚠️ Our travel planning service is experiencing high load or delay.\n\n"
                    "Please reply with *Confirm* to retry, or *New trip* to start fresh."
                )
            )
            return False
        except Exception as exc:
            logger.exception("Unexpected error in trip generation for %s: %s", wa_id, exc)
            session.state = ConversationState.ERROR
            await redis_store.save_session(session)
            await whatsapp_client.send_message_payload(
                build_text_message(
                    wa_id,
                    "⚠️ An unexpected error occurred while building your itinerary. Please try again in a few moments."
                )
            )
            return False


trip_service = TripService()
