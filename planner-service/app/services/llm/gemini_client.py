"""
Gemini LLM client — uses the official google-genai Python SDK.

Responsibilities:
  - Load API key from settings.
  - Configure the model with structured JSON output.
  - Send system prompt + TripContext JSON as separate parts.
  - Return the raw parsed dict for the caller to validate.
  - Handle and wrap all SDK errors without leaking keys or internals.
"""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"


class GeminiClient:
    """
    Stateless Gemini JSON generation client.
    Initialised lazily — no API call at construction time.
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to planner-service/.env"
            )
        self._client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("GeminiClient initialised with model %s", _MODEL)

    async def generate_json(
        self,
        system_prompt: str,
        user_data: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a JSON object from the model.

        Args:
            system_prompt: Permanent planning rules (never contains user data).
            user_data:     Structured TripContext payload as a plain dict.
            json_schema:   Pydantic-generated JSON schema for constrained output.

        Returns:
            Parsed dict from the model response.

        Raises:
            GeminiError: On API error, timeout, or non-JSON response.
        """
        user_content = (
            "Here is the TripContext for this planning request:\n\n"
            + json.dumps(user_data, ensure_ascii=False, indent=2)
            + "\n\nProduce the Itinerary JSON as specified."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=json_schema,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=_MODEL,
                contents=user_content,
                config=config,
            )
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise GeminiError("Gemini API request failed.") from exc

        try:
            raw_text = response.text
        except Exception as exc:
            logger.error("Gemini response has no text: %s", exc)
            raise GeminiError("Gemini returned an empty response.") from exc

        if not raw_text or not raw_text.strip():
            raise GeminiError("Gemini returned an empty response body.")

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Gemini non-JSON response: %s", raw_text[:500])
            raise GeminiError("Gemini returned non-JSON output.") from exc


class GeminiError(Exception):
    """Raised when the Gemini client cannot produce a valid response."""
    pass
