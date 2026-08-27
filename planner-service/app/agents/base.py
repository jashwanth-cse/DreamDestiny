"""
BaseAgent — abstract contract for all agents in this service.

Every agent must:
  - Accept a TripContext as its only factual input.
  - Return a strictly validated Pydantic model.
  - Never import or call service clients directly.
  - Be independently testable with a mocked TripContext.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from app.schemas.context import TripContext

T = TypeVar("T")


class BaseAgent(ABC, Generic[T]):
    """
    Generic base for all planning agents.

    Subclasses define the output type T and implement plan().
    """

    @abstractmethod
    async def plan(self, context: TripContext) -> T:
        """
        Produce a structured plan given a fully assembled TripContext.

        Args:
            context: The normalized, validated TripContext from the orchestrator.

        Returns:
            A strictly validated Pydantic model of type T.

        Raises:
            AgentError: On LLM failure, timeout, or schema validation failure.
        """
        ...


class AgentError(Exception):
    """
    Raised when an agent cannot produce a valid plan.
    Wraps upstream errors without leaking API keys or internal details.
    """
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause
