"""
Environment-driven configuration using pydantic-settings.
All values are loaded from the .env file at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SerpApi
    serpapi_api_key: str

    # Cache
    hotel_cache_ttl_hours: int = 24
    hotel_db_path: str = ""

    # CORS
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Single instance reused across the app
settings = Settings()
