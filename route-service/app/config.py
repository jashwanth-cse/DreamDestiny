"""
Environment configuration for the Route Service.
All values loaded from .env at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Google Maps API key — used for the Routes API
    google_maps_api_key: str

    # CORS
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
