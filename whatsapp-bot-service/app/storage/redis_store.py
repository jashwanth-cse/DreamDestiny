"""
Redis storage client for short-lived active conversation sessions and distributed locks.
Supports async operations with connection pooling and an in-memory fallback for offline test suites.
"""

import json
import logging
from typing import Optional
from contextlib import asynccontextmanager

from app.schemas.conversation import UserSession
from app.config import settings

logger = logging.getLogger(__name__)

# Optional Redis import
try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class RedisStore:
    def __init__(self, redis_url: str = settings.redis_url):
        self._url = redis_url
        self._client: Optional[redis.Redis] = None
        self._memory_cache: dict[str, str] = {}  # In-memory fallback
        self._locks: set[str] = set()

    async def connect(self):
        if redis is not None and self._url:
            try:
                self._client = redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    password=settings.redis_password or None,
                    socket_timeout=settings.request_timeout_seconds,
                )
                await self._client.ping()
                logger.info("Successfully connected to Redis instance at %s", self._url)
                return
            except Exception as e:
                logger.warning("Could not connect to Redis at %s: %s. Using in-memory fallback.", self._url, e)
                self._client = None
        else:
            logger.info("Redis package or URL not available. Using in-memory fallback store.")

    async def close(self):
        if self._client:
            await self._client.close()

    def _session_key(self, wa_id: str) -> str:
        return f"travel:conversation:{wa_id}"

    def _lock_key(self, wa_id: str) -> str:
        return f"travel:lock:{wa_id}"

    def _idempotency_key(self, message_id: str) -> str:
        return f"travel:idempotency:{message_id}"

    async def get_session(self, wa_id: str) -> Optional[UserSession]:
        """Fetch active user session from Redis, returning None on cache miss."""
        key = self._session_key(wa_id)
        try:
            if self._client:
                data = await self._client.get(key)
            else:
                data = self._memory_cache.get(key)

            if not data:
                return None
            return UserSession.model_validate_json(data)
        except Exception as e:
            logger.error("Error reading session for %s from Redis: %s", wa_id, e)
            return None

    async def save_session(self, session: UserSession, ttl_seconds: int = settings.conversation_ttl_seconds):
        """Persist or update active user session with TTL."""
        key = self._session_key(session.wa_id)
        payload = session.model_dump_json()
        try:
            if self._client:
                await self._client.set(key, payload, ex=ttl_seconds)
            else:
                self._memory_cache[key] = payload
        except Exception as e:
            logger.error("Error saving session for %s to Redis: %s", session.wa_id, e)

    async def delete_session(self, wa_id: str):
        """Remove active session from Redis."""
        key = self._session_key(wa_id)
        try:
            if self._client:
                await self._client.delete(key)
            else:
                self._memory_cache.pop(key, None)
        except Exception as e:
            logger.error("Error deleting session for %s: %s", wa_id, e)

    @asynccontextmanager
    async def user_lock(self, wa_id: str, timeout_seconds: float = settings.lock_timeout_seconds):
        """
        Per-user distributed lock to prevent race conditions from concurrent webhook events.
        Automatically releases after message execution or upon timeout expiry.
        """
        lock_key = self._lock_key(wa_id)
        lock_acquired = False
        try:
            if self._client:
                # Use Redis SET NX PX
                lock = self._client.lock(lock_key, timeout=timeout_seconds, blocking_timeout=2.0)
                acquired = await lock.acquire()
                if acquired:
                    lock_acquired = True
                    yield True
                else:
                    logger.warning("Could not acquire lock for user %s within timeout", wa_id)
                    yield False
            else:
                # In-memory lock simulation
                if lock_key not in self._locks:
                    self._locks.add(lock_key)
                    lock_acquired = True
                    yield True
                else:
                    yield False
        finally:
            if lock_acquired:
                try:
                    if self._client and lock:
                        await lock.release()
                    else:
                        self._locks.discard(lock_key)
                except Exception as exc:
                    logger.warning("Failed to release lock for %s: %exc", wa_id, exc)

    async def is_message_processed(self, message_id: str) -> bool:
        """Check if WhatsApp message ID was already processed (Idempotency)."""
        key = self._idempotency_key(message_id)
        try:
            if self._client:
                val = await self._client.get(key)
                return val is not None
            return key in self._memory_cache
        except Exception:
            return False

    async def mark_message_processed(self, message_id: str, ttl_seconds: int = settings.idempotency_ttl_seconds):
        """Record message ID to prevent duplicate processing on webhook retries."""
        key = self._idempotency_key(message_id)
        try:
            if self._client:
                await self._client.set(key, "processed", ex=ttl_seconds)
            else:
                self._memory_cache[key] = "processed"
        except Exception as e:
            logger.error("Error recording idempotency for %s: %s", message_id, e)


redis_store = RedisStore()
