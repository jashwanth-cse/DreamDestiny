"""
Planner Service — environment configuration.
All service base URLs and settings loaded from .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Downstream service URLs ────────────────────────────────────────────
    tourism_service_url: str = "http://localhost:8001"
    transport_bus_service_url: str = "http://localhost:8004"
    transport_train_service_url: str = "http://localhost:8005"
    hotel_service_url: str = "http://localhost:8002"
    route_service_url: str = "http://localhost:8003"

    # ── HTTP client settings ───────────────────────────────────────────────
    http_timeout: float = 20.0        # seconds per downstream call

    # ── Gemini / LLM ──────────────────────────────────────────────────────
    gemini_api_key: str = ""          # Required for POST /plan
    llm_timeout: float = 60.0         # seconds — LLM calls take longer

    # ── CORS ───────────────────────────────────────────────────────────────
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
