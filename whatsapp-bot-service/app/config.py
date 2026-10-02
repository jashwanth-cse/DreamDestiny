"""
Application configuration for the WhatsApp Bot Service.
Loads from environment variables and supports .env files.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    log_level: str = "INFO"

    # Meta WhatsApp Cloud API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "dream_destiny_verify_token"
    whatsapp_api_version: str = "v20.0"
    whatsapp_app_secret: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_password: Optional[str] = None

    # Firestore
    firebase_project_id: Optional[str] = None
    google_application_credentials: Optional[str] = None

    # Backend Planner Gateway URL (Points to planner-service or NGINX gateway)
    planner_gateway_url: str = "http://planner-service:8000"
    bedrock_api_key: Optional[str] = None
    google_maps_api_key: Optional[str] = None

    # Timeouts & TTLs
    conversation_ttl_seconds: int = 172800  # 48 hours
    request_timeout_seconds: float = 30.0
    lock_timeout_seconds: float = 10.0
    idempotency_ttl_seconds: int = 86400  # 24 hours

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
