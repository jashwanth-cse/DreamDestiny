"""
Gemini LLM client — uses the official google-genai Python SDK.

Responsibilities:
  - Load API key from settings.
  - Configure the model with structured JSON output.
  - Send system prompt + TripContext JSON as separate parts.
  - Return the raw parsed dict for the caller to validate.
  - Handle and wrap all SDK errors without leaking keys or internals.
"""

import asyncio
import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

import time

_PRIMARY_MODEL = "gemma-4-26b-a4b-it"
_BACKUP_MODEL = "gemini-3.8-flash"
_CIRCUIT_DOWN_UNTIL = 0

class GeminiClient:
    """
    Stateless Gemini JSON generation client with Circuit Breaker.
    Initialised lazily ?" no API call at construction time.
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to planner-service/.env"
            )
        self._client = genai.Client(api_key=settings.gemini_api_key)
        logger.info(f"GeminiClient initialised with Primary: {_PRIMARY_MODEL}, Backup: {_BACKUP_MODEL}")

    async def generate_json(
        self,
        system_prompt: str,
        user_data: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a JSON object from the model with Fallback capabilities.
        """
        global _CIRCUIT_DOWN_UNTIL

        # Gemma models often reject `system_instruction` with 400/500 errors.
        # So we inject the system instructions directly into the top of the user prompt.
        combined_content = (
            f"{system_prompt}\n\n"
            "Here is the TripContext for this planning request:\n\n"
            + json.dumps(user_data, ensure_ascii=False, indent=2)
            + "\n\nProduce the Itinerary JSON as specified."
        )

        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=json_schema,
        )

        response = None
        
        # Decide which model to use
        if time.time() < _CIRCUIT_DOWN_UNTIL:
            current_model = _BACKUP_MODEL
            logger.info(f"Primary model is in cool-down. Routing to {_BACKUP_MODEL}")
        else:
            current_model = _PRIMARY_MODEL

        try:
            response = await self._client.aio.models.generate_content(
                model=current_model,
                contents=combined_content,
                config=config,
            )
        except Exception as exc:
            err_str = str(exc)
            if current_model == _PRIMARY_MODEL:
                logger.warning(f"Primary model {_PRIMARY_MODEL} failed: {exc}. Tripping circuit breaker for 60s and falling back to {_BACKUP_MODEL}.")
                _CIRCUIT_DOWN_UNTIL = time.time() + 60
                
                # Retry immediately with backup
                try:
                    response = await self._client.aio.models.generate_content(
                        model=_BACKUP_MODEL,
                        contents=combined_content,
                        config=config,
                    )
                except Exception as backup_exc:
                    logger.error("Backup Gemini API error: %s", backup_exc)
                    raise GeminiError("Gemini API backup request failed.") from backup_exc
            else:
                logger.error("Gemini API error on backup: %s", exc)
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
