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
    transport_flight_service_url: str = "http://localhost:8006"
    flight_service_url: str = "http://localhost:8006"
    hotel_service_url: str = "http://localhost:8002"
    route_service_url: str = "http://localhost:8003"

    # ── HTTP client settings ───────────────────────────────────────────────
    http_timeout: float = 20.0        # seconds per downstream call

    # ── Gemini / LLM ──────────────────────────────────────────────────────
    bedrock_api_key: str = ""          # Required for POST /plan
    bedrock_converse_model_id: str = ""  # A Converse-capable model, separate from Gemma 4
    bedrock_region: str = ""             # Region hosting the Converse model
    google_maps_api_key: str = ""     # Nearby Trip Rescue Places, Geocoding and Routes
    llm_timeout: float = 60.0         # seconds — LLM calls take longer

    # ── CORS ───────────────────────────────────────────────────────────────
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
