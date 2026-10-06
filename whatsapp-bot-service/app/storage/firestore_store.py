"""
Firestore storage client for durable persistence of users, conversations, trips, and itineraries.
Adheres to the document hierarchy in Section 8 & 29 of the specification.
Includes in-memory simulation for local testing when credentials are not configured.
"""

import logging
from typing import Optional, Dict, Any, List

from app.schemas.conversation import (
    UserRecord,
    ConversationRecord,
    MessageRecord,
    TripRecord,
    ItineraryVersionRecord,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Optional Google Cloud Firestore import
try:
    from google.cloud import firestore
except ImportError:
    firestore = None


class FirestoreStore:
    def __init__(self, project_id: Optional[str] = settings.firebase_project_id):
        self._project_id = project_id
        self._db = None
        # In-memory persistence fallback
        self._users: Dict[str, Dict[str, Any]] = {}
        self._conversations: Dict[str, Dict[str, Any]] = {}
        self._messages: Dict[str, List[Dict[str, Any]]] = {}
        self._trips: Dict[str, List[Dict[str, Any]]] = {}
        self._itineraries: Dict[str, List[Dict[str, Any]]] = {}

    def connect(self):
        if firestore is None:
            logger.info("Firestore package not available. Using in-memory store for durable records.")
            return

        credentials = None

        # 1. Direct Private Key + Client Email authentication from environment
        if settings.firebase_private_key and settings.firebase_client_email:
            try:
                from google.oauth2 import service_account
                clean_key = settings.firebase_private_key.replace("\\n", "\n").strip()
                if clean_key.startswith('"') and clean_key.endswith('"'):
                    clean_key = clean_key[1:-1].replace("\\n", "\n").strip()

                proj = self._project_id or settings.firebase_project_id
                info = {
                    "type": "service_account",
                    "project_id": proj,
                    "private_key": clean_key,
                    "client_email": settings.firebase_client_email.strip(),
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                credentials = service_account.Credentials.from_service_account_info(info)
                logger.info("Successfully constructed Firestore credentials from private key.")
            except Exception as e:
                logger.warning("Could not construct credentials from FIREBASE_PRIVATE_KEY: %s", e)

        # 2. Complete JSON string in environment variable
        elif settings.firebase_service_account_json:
            try:
                import json
                from google.oauth2 import service_account
                raw_json = settings.firebase_service_account_json.strip()
                info = json.loads(raw_json)
                credentials = service_account.Credentials.from_service_account_info(info)
                logger.info("Successfully loaded Firestore credentials from JSON string.")
            except Exception as e:
                logger.warning("Could not construct credentials from FIREBASE_SERVICE_ACCOUNT_JSON: %s", e)

        # 3. Initialize Firestore Client
        if credentials:
            try:
                proj_id = self._project_id or settings.firebase_project_id
                self._db = firestore.AsyncClient(project=proj_id, credentials=credentials)
                logger.info("Connected to Google Cloud Firestore with project %s using service account %s", proj_id, settings.firebase_client_email or "custom")
                return
            except Exception as e:
                logger.warning("Could not initialize Firestore Client with credentials: %s. Using in-memory store.", e)
                self._db = None

        elif self._project_id or settings.google_application_credentials:
            try:
                self._db = firestore.AsyncClient(project=self._project_id)
                logger.info("Connected to Google Cloud Firestore with default credentials for project %s", self._project_id)
                return
            except Exception as e:
                logger.warning("Could not initialize Firestore Client with default credentials: %s. Using in-memory store.", e)
                self._db = None
        else:
            logger.info("Firestore credentials not configured. Using in-memory store for durable records.")

    async def save_user(self, user: UserRecord):
        """Upsert user in users/{wa_id}"""
        data = user.model_dump()
        if self._db:
            try:
                doc_ref = self._db.collection("users").document(user.wa_id)
                await doc_ref.set(data, merge=True)
            except Exception as e:
                logger.error("Error saving user to Firestore: %s", e)
        else:
            self._users[user.wa_id] = data

    async def get_user(self, wa_id: str) -> Optional[UserRecord]:
        """Fetch user by WhatsApp ID"""
        if self._db:
            try:
                doc = await self._db.collection("users").document(wa_id).get()
                if doc.exists:
                    return UserRecord.model_validate(doc.to_dict())
            except Exception as e:
                logger.error("Error fetching user from Firestore: %s", e)
                return None
        else:
            if wa_id in self._users:
                return UserRecord.model_validate(self._users[wa_id])
        return None

    async def save_conversation(self, conv: ConversationRecord):
        """Save conversation record in users/{wa_id}/conversations/{conv_id}"""
        data = conv.model_dump()
        if self._db:
            try:
                doc_ref = (
                    self._db.collection("users")
                    .document(conv.wa_id)
                    .collection("conversations")
                    .document(conv.conversation_id)
                )
                await doc_ref.set(data, merge=True)
            except Exception as e:
                logger.error("Error saving conversation to Firestore: %s", e)
        else:
            self._conversations[conv.conversation_id] = data

    async def save_message(self, wa_id: str, conversation_id: str, msg: MessageRecord):
        """Append message to audit subcollection users/{wa_id}/conversations/{conv_id}/messages/{msg_id}"""
        data = msg.model_dump()
        if self._db:
            try:
                doc_ref = (
                    self._db.collection("users")
                    .document(wa_id)
                    .collection("conversations")
                    .document(conversation_id)
                    .collection("messages")
                    .document(msg.message_id)
                )
                await doc_ref.set(data)
            except Exception as e:
                logger.error("Error saving message audit in Firestore: %s", e)
        else:
            if conversation_id not in self._messages:
                self._messages[conversation_id] = []
            self._messages[conversation_id].append(data)

    async def save_trip(self, trip: TripRecord):
        """Save trip record in users/{wa_id}/trips/{trip_id}"""
        data = trip.model_dump()
        if self._db:
            try:
                doc_ref = (
                    self._db.collection("users")
                    .document(trip.wa_id)
                    .collection("trips")
                    .document(trip.trip_id)
                )
                await doc_ref.set(data, merge=True)
            except Exception as e:
                logger.error("Error saving trip to Firestore: %s", e)
        else:
            if trip.wa_id not in self._trips:
                self._trips[trip.wa_id] = []
            self._trips[trip.wa_id].append(data)

    async def save_itinerary_version(self, wa_id: str, trip_id: str, version: ItineraryVersionRecord):
        """Save versioned itinerary in users/{wa_id}/trips/{trip_id}/itineraries/{version_id}"""
        data = version.model_dump()
        if self._db:
            try:
                doc_ref = (
                    self._db.collection("users")
                    .document(wa_id)
                    .collection("trips")
                    .document(trip_id)
                    .collection("itineraries")
                    .document(version.version_id)
                )
                await doc_ref.set(data)
            except Exception as e:
                logger.error("Error saving itinerary version: %s", e)
        else:
            if trip_id not in self._itineraries:
                self._itineraries[trip_id] = []
            self._itineraries[trip_id].append(data)

    async def get_latest_trip(self, wa_id: str, destination: Optional[str] = None) -> Optional[TripRecord]:
        """
        Retrieve user's latest trip, optionally filtered by destination city.
        Supports conversation recovery when Redis active session has expired.
        """
        if self._db:
            try:
                query = self._db.collection("users").document(wa_id).collection("trips")
                if destination:
                    query = query.where("destination", "==", destination)
                query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(1)
                docs = await query.get()
                if docs:
                    return TripRecord.model_validate(docs[0].to_dict())
            except Exception as e:
                logger.error("Error querying trips from Firestore: %s", e)
                return None
        else:
            trips = self._trips.get(wa_id, [])
            if destination:
                matching = [t for t in trips if t.get("destination", "").lower() == destination.lower()]
                if matching:
                    return TripRecord.model_validate(matching[-1])
            elif trips:
                return TripRecord.model_validate(trips[-1])
        return None

    async def get_latest_itinerary(self, wa_id: str, trip_id: str) -> Optional[ItineraryVersionRecord]:
        """Fetch the latest active itinerary version for a trip."""
        if self._db:
            try:
                query = (
                    self._db.collection("users")
                    .document(wa_id)
                    .collection("trips")
                    .document(trip_id)
                    .collection("itineraries")
                    .where("is_current", "==", True)
                    .limit(1)
                )
                docs = await query.get()
                if docs:
                    return ItineraryVersionRecord.model_validate(docs[0].to_dict())
            except Exception as e:
                logger.error("Error querying itinerary from Firestore: %s", e)
                return None
        else:
            versions = self._itineraries.get(trip_id, [])
            currents = [v for v in versions if v.get("is_current")]
            if currents:
                return ItineraryVersionRecord.model_validate(currents[-1])
            elif versions:
                return ItineraryVersionRecord.model_validate(versions[-1])
        return None

    async def save_customer_review(
        self,
        reviewer_name: str,
        rating: int,
        destination: str,
        review_text: Optional[str] = None,
    ) -> bool:
        """
        Stores public customer reviews in Firestore for showcase on the website.
        Does NOT store the user's private phone number / wa_id so it can be queried publicly.
        Collection: 'reviews'
        """
        from datetime import datetime, timezone
        review_doc = {
            "reviewer_name": reviewer_name or "Anonymous Traveler",
            "rating": max(1, min(5, int(rating))),
            "destination": destination or "Incredible India",
            "review_text": review_text or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "published",
        }
        if self._db:
            try:
                await self._db.collection("reviews").add(review_doc)
                logger.info("Saved %d-star review from %s to Firestore reviews collection", rating, reviewer_name)
                return True
            except Exception as e:
                logger.error("Error saving review to Firestore: %s", e)
                return False
        else:
            if not hasattr(self, "_reviews"):
                self._reviews = []
            self._reviews.append(review_doc)
            logger.info("[OFFLINE REVIEWS] Saved review locally: %s", review_doc)
            return True


firestore_store = FirestoreStore()
