"""
Firestore Persistence Service for TrainWatch Availability Load-Test Service.

Persists test run summaries, deduplication metrics, latency percentiles,
and request breakdowns to Google Cloud Firestore with an offline in-memory fallback.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from app.config import settings
from app.models.schemas import RunSummary

logger = logging.getLogger(__name__)


class FirestoreStorageService:
    """Handles persistence of load-test runs to Firestore."""

    def __init__(self):
        self._client = None
        self._initialized = False
        self._in_memory_fallback: List[Dict[str, Any]] = []
        self._init_client()

    def _init_client(self):
        if not settings.enable_firestore:
            logger.info("Firestore persistence disabled via configuration.")
            return

        try:
            from google.cloud import firestore
            self._client = firestore.Client(
                project=settings.gcp_project_id,
                database=settings.firestore_database,
            )
            self._initialized = True
            logger.info(
                f"Connected to Firestore: project='{settings.gcp_project_id}', "
                f"collection='{settings.firestore_collection}'"
            )
        except Exception as exc:
            logger.warning(
                f"Firestore client initialization skipped ({exc}). "
                f"Using in-memory fallback mode."
            )
            self._client = None
            self._initialized = False

    @property
    def is_connected(self) -> bool:
        """Returns True if live Firestore client is active."""
        return self._initialized and self._client is not None

    async def save_run(self, summary: RunSummary) -> Tuple[bool, Optional[str]]:
        """
        Persists a completed RunSummary to Firestore.
        Returns a tuple of (persisted_live, document_id).
        """
        doc_data = summary.model_dump()
        doc_data["stored_at"] = datetime.utcnow().isoformat() + "Z"

        if self.is_connected:
            try:
                collection_ref = self._client.collection(settings.firestore_collection)
                doc_ref = collection_ref.document(summary.run_id)
                doc_ref.set(doc_data)
                logger.info(
                    f"Run {summary.run_id} persisted to Firestore collection '{settings.firestore_collection}'"
                )
                return True, doc_ref.id
            except Exception as exc:
                logger.error(f"Failed to persist run {summary.run_id} to Firestore: {exc}")
                self._in_memory_fallback.append(doc_data)
                return False, summary.run_id
        else:
            self._in_memory_fallback.append(doc_data)
            logger.info(f"Run {summary.run_id} stored in in-memory fallback storage.")
            return False, summary.run_id

    async def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves the most recent test runs."""
        if self.is_connected:
            try:
                from google.cloud import firestore
                collection_ref = self._client.collection(settings.firestore_collection)
                query = (
                    collection_ref.order_by("timestamp", direction=firestore.Query.DESCENDING)
                    .limit(limit)
                )
                docs = query.stream()
                return [d.to_dict() for d in docs]
            except Exception as exc:
                logger.warning(f"Failed to read from Firestore: {exc}. Reading fallback storage.")

        # Fallback to in-memory list
        return list(reversed(self._in_memory_fallback[-limit:]))

    async def get_run_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific run document by its UUID."""
        if self.is_connected:
            try:
                doc = (
                    self._client.collection(settings.firestore_collection)
                    .document(run_id)
                    .get()
                )
                if doc.exists:
                    return doc.to_dict()
            except Exception as exc:
                logger.warning(f"Firestore get_run_by_id error: {exc}")

        for r in self._in_memory_fallback:
            if r.get("run_id") == run_id:
                return r
        return None


# Global singleton
firestore_storage = FirestoreStorageService()


def get_firestore_storage() -> FirestoreStorageService:
    return firestore_storage
