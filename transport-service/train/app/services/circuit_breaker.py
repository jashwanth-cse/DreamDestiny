"""
In-process Circuit Breaker

Protects upstream train availability APIs and downstream microservices from cascading
failures during upstream outages.
"""

from __future__ import annotations

import time
import logging
from enum import Enum
from typing import Optional

from app.exceptions import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operations
    OPEN = "OPEN"            # Fail-fast, do not call upstream
    HALF_OPEN = "HALF_OPEN"  # Testing upstream recovery


class CircuitBreaker:
    """
    Thread-safe / Async-safe in-process circuit breaker.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 15.0,
        name: str = "upstream-availability"
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.monotonic()

    def before_call(self) -> None:
        """
        Check whether a call is allowed through.
        Raises CircuitBreakerOpenError if the breaker is OPEN.
        Transitions OPEN -> HALF_OPEN when reset_timeout has elapsed.
        """
        now = time.monotonic()

        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time) >= self.reset_timeout:
                logger.info(
                    f"Circuit breaker '{self.name}' transitioning from OPEN to HALF_OPEN after {self.reset_timeout}s"
                )
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
            else:
                remaining = self.reset_timeout - (now - (self.last_failure_time or now))
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. Upstream temporarily suspended ({remaining:.1f}s remaining)."
                )

    def record_success(self) -> None:
        """Record a successful call, resetting failure counts."""
        if self.state != CircuitState.CLOSED:
            logger.info(f"Circuit breaker '{self.name}' recovered: state set to CLOSED.")
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = None
        self.last_state_change = time.monotonic()

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record an upstream failure (timeout or 5xx error)."""
        now = time.monotonic()
        self.failure_count += 1
        self.last_failure_time = now

        if self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit breaker '{self.name}' failed during HALF_OPEN probe. Re-opening for {self.reset_timeout}s."
            )
            self.state = CircuitState.OPEN
            self.last_state_change = now
        elif self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.error(
                    f"Circuit breaker '{self.name}' TRIPPED to OPEN after {self.failure_count} consecutive failures. "
                    f"Last error: {error}"
                )
            self.state = CircuitState.OPEN
            self.last_state_change = now
