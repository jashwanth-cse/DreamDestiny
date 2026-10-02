import time
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self):
        self.primary_model_name = "gemma-4-26b-a4b-it"
        self.backup_model_name = "gemini-3.8-flash"
        self.primary_down_until = 0
        self.circuit_break_duration = 60  # seconds

    def is_primary_healthy(self):
        return time.time() >= self.primary_down_until

    def mark_primary_failure(self, error):
        logger.warning(f"Primary model ({self.primary_model_name}) failed with error: {error}")
        logger.warning(f"Tripping circuit breaker for {self.circuit_break_duration} seconds.")
        self.primary_down_until = time.time() + self.circuit_break_duration

    async def generate_content_async(self, prompt, **kwargs):
        """Attempts to generate content with primary, falls back to backup."""
        if self.is_primary_healthy():
            model = genai.GenerativeModel(self.primary_model_name)
            try:
                return await model.generate_content_async(prompt, **kwargs)
            except Exception as e:
                self.mark_primary_failure(e)
                # Fallback on failure
                logger.info(f"Falling back to backup model: {self.backup_model_name}")
                backup_model = genai.GenerativeModel(self.backup_model_name)
                return await backup_model.generate_content_async(prompt, **kwargs)
        else:
            # Circuit breaker is tripped, use backup directly
            backup_model = genai.GenerativeModel(self.backup_model_name)
            return await backup_model.generate_content_async(prompt, **kwargs)

# Global singleton router for the bot service
global_llm_router = LLMRouter()
