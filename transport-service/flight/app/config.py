"""
Flight Service — Configuration settings.
Loads environment variables from local .env or root .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SerpApi Google Flights API Key
    serpapi_api_key: str = ""

    # Service Port and Network Settings
    flight_service_port: int = 8006
    http_timeout: float = 30.0
    default_currency: str = "INR"
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
