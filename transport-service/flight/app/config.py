"""
Flight Service — Configuration settings.
Loads environment variables from local .env or root .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SerpApi Google Flights API Key
    serpapi_api_key: str = ""

    # Google Maps / Geocoding API Key (used for geo-nearest airport resolution)
    # Shared with route-service; read from root .env via Docker env injection.
    google_maps_api_key: str = ""

    # Geo-nearest airport settings
    max_airport_radius_km: float = 500.0       # max search radius in km
    geocoding_cache_ttl: float = 86_400.0      # geocoding cache TTL in seconds (24 h)
    geocoding_cache_max_size: int = 512        # max cached city entries

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
