"""
Application Configuration for TrainWatch Availability Load-Test Service.

Reads environment variables with production-ready defaults and guardrails.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service Settings loaded from environment or .env file."""

    # GCP Project & Firestore
    gcp_project_id: str = "trainwatch"
    firestore_database: str = "(default)"
    firestore_collection: str = "trainwatch_load_test_runs"
    enable_firestore: bool = True

    # Target Availability Endpoint (reuses production service without modification)
    target_availability_url: str = (
        "https://dreamdestiny.cloud.run/api/v1/trains/availability"
    )

    # Optional defense-in-depth API Key (in addition to Cloud Run IAM OIDC)
    service_api_key: Optional[str] = None

    # Safety Guardrails (prevents runaway requests / billing spikes)
    default_scenario: str = "balanced"
    default_concurrency: int = 20
    max_allowed_concurrency: int = 50
    default_total_requests: int = 60
    max_allowed_requests: int = 200
    request_timeout_seconds: float = 10.0
    run_deadline_seconds: float = 120.0

    # IRCTC Blackout Windows (Maintenance & Tatkal rate-limit protection)
    enforce_blackout_windows: bool = True
    timezone: str = "Asia/Kolkata"

    # Networking / Server
    port: int = 8080
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
