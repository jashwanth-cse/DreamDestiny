import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

class BedrockLLMClient:
    """
    Stateless Bedrock (OpenAI API compatible) JSON generation client.
    """

    def __init__(self) -> None:
        if not settings.bedrock_api_key:
            raise RuntimeError(
                "BEDROCK_API_KEY is not set. Add it to planner-service/.env"
            )
        self._client = AsyncOpenAI(
            api_key=settings.bedrock_api_key,
            base_url="https://bedrock-mantle.us-east-1.api.aws/openai/v1"
        )
        self._model = "google.gemma-4-31b"
        logger.info(f"BedrockLLMClient initialised with Model: {self._model}")

    async def generate_json(
        self,
        system_prompt: str,
        user_data: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a JSON object from the model via Bedrock.
        """
        user_content = (
            f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
            "Here is the TripContext for this planning request:\n\n"
            + json.dumps(user_data, ensure_ascii=False, indent=2)
            + "\n\nCRITICAL: You MUST output exactly ONE valid JSON object conforming strictly to this JSON schema. Do not omit any required fields:\n\n"
            + json.dumps(json_schema, indent=2)
            + "\n\nProduce the Itinerary JSON now. ONLY output valid JSON. No markdown backticks. No extra text."
        )

        messages = [
            {"role": "user", "content": user_content}
        ]

        response = None
        
        try:
            # Gemma 4 31b supports JSON response format in OpenAI compatibility
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
                max_tokens=8192
            )
        except Exception as exc:
            logger.error("Bedrock API error: %s", exc)
            raise LLMError("Bedrock API request failed.") from exc

        try:
            raw_text = response.choices[0].message.content
            logger.info("Bedrock raw text response length: %d", len(raw_text) if raw_text else 0)
            logger.debug("Bedrock raw text: %s", raw_text)
        except Exception as exc:
            logger.error("Bedrock response has no text: %s", exc)
            raise LLMError("Bedrock returned an empty response.") from exc

        if not raw_text or not raw_text.strip():
            raise LLMError("Bedrock returned an empty response body.")

        import re
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text)
            
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Bedrock non-JSON response: %s", raw_text[:500])
            raise LLMError("Bedrock returned non-JSON output.") from exc

class LLMError(Exception):
    """Raised when the LLM client cannot produce a valid response."""
    pass
