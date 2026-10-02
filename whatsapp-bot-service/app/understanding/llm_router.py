import time
import logging
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self):
        # Bedrock models don't really have the same fallback issue if it's stable, 
        # but we can keep the class structure for consistency.
        self.model_name = "google.gemma-4-31b"
        self._client = None
        if settings.bedrock_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.bedrock_api_key,
                base_url="https://bedrock-mantle.us-east-1.api.aws/openai/v1"
            )

    async def generate_content_async(self, prompt, **kwargs):
        """Generates content via Bedrock OpenAI compatibility."""
        if not self._client:
            logger.warning("Bedrock API key not configured!")
            # Mock an empty response structure for safety
            class MockResponse:
                @property
                def text(self): return ""
            return MockResponse()

        # Build chat completions kwargs
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                **kwargs
            )
            content = response.choices[0].message.content
            
            # Wrap response to match old SDK's `response.text` interface
            class BedrockResponse:
                def __init__(self, text):
                    self.text = text
            return BedrockResponse(content)
        except Exception as e:
            logger.error(f"Bedrock LLM failed: {e}")
            raise e

# Global singleton router for the bot service
global_llm_router = LLMRouter()
