"""
Configuration for Transport Service

All API endpoints, credentials, timeouts, and headers are centralized here.
Environment variables can override defaults in production.
"""

import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class IxigoConfig:

    # ----------------------------
    # API URLs
    # ----------------------------

    STATION_API: str = os.getenv(
        "IXIGO_STATION_API",
        "https://www.ixigo.com/action/content/trainstation"
    )

    TRAIN_API: str = os.getenv(
        "CONFIRMTKT_TRAIN_API",
        "https://ixigotrainsapi.confirmtkt.com/api/v1/trains/search"
    )

    AVAILABILITY_API: str = os.getenv(
        "CONFIRMTKT_AVAILABILITY_API",
        "https://ixigotrainsapi.confirmtkt.com/api/v1/availability/fetchAvailability"
    )

    SCHEDULE_API: str = os.getenv(
        "REDBUS_SCHEDULE_API",
        "https://www.redbus.in/rails/api/getTrainScheduleDetails"
    )

    # ----------------------------
    # Upstream Credentials
    # ----------------------------
    STATION_API_KEY: str = os.getenv("IXIGO_STATION_API_KEY", "ixiweb!2$")
    STATION_CLIENT_ID: str = os.getenv("IXIGO_STATION_CLIENT_ID", "ixiweb")

    TRAIN_API_KEY: str = os.getenv("CONFIRMTKT_API_KEY", "iximweb!2$")
    TRAIN_CLIENT_ID: str = os.getenv("CONFIRMTKT_CLIENT_ID", "iximweb")

    # ----------------------------
    # Timeouts & Pooling (in seconds)
    # ----------------------------
    CONNECT_TIMEOUT: float = float(os.getenv("UPSTREAM_CONNECT_TIMEOUT", "4.0"))
    READ_TIMEOUT: float = float(os.getenv("UPSTREAM_READ_TIMEOUT", "8.0"))
    WRITE_TIMEOUT: float = float(os.getenv("UPSTREAM_WRITE_TIMEOUT", "4.0"))
    POOL_TIMEOUT: float = float(os.getenv("UPSTREAM_POOL_TIMEOUT", "4.0"))

    MAX_KEEPALIVE_CONNECTIONS: int = int(os.getenv("MAX_KEEPALIVE_CONNECTIONS", "30"))
    MAX_CONNECTIONS: int = int(os.getenv("MAX_CONNECTIONS", "100"))

    # ----------------------------
    # Resilience & Rate Bounds
    # ----------------------------
    MAX_RETRIES: int = int(os.getenv("AVAILABILITY_MAX_RETRIES", "1"))
    BACKOFF_FACTOR: float = float(os.getenv("AVAILABILITY_BACKOFF_FACTOR", "0.2"))
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
    CIRCUIT_BREAKER_RESET_TIMEOUT: float = float(os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT", "15.0"))

    # Bounded concurrency across simultaneous availability requests
    MAX_CONCURRENT_AVAILABILITY: int = int(os.getenv("MAX_CONCURRENT_AVAILABILITY", "50"))

    # In-memory snapshot cache TTL (seconds) for read-only availability
    AVAILABILITY_CACHE_TTL: int = int(os.getenv("AVAILABILITY_CACHE_TTL", "60"))

    # Train Schedule Cache TTL (seconds) - default 24 hours
    SCHEDULE_CACHE_TTL: int = int(os.getenv("SCHEDULE_CACHE_TTL", "86400"))

    # Bounded concurrency across simultaneous schedule requests
    MAX_CONCURRENT_SCHEDULE: int = int(os.getenv("MAX_CONCURRENT_SCHEDULE", "30"))

    # ----------------------------
    # Dynamic Headers Methods
    # ----------------------------
    def get_station_headers(self) -> Dict[str, str]:
        """Returns fresh station headers with distinct device/request UUIDs."""
        return {
            "Accept": "*/*",
            "ApiKey": self.STATION_API_KEY,
            "ClientId": self.STATION_CLIENT_ID,
            "DeviceId": uuid.uuid4().hex,
            "Uuid": uuid.uuid4().hex,
            "IxiSrc": "ixiweb",
            "Referer": "https://www.ixigo.com/train-stations",
            "Origin": "https://www.ixigo.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

    def get_train_headers(self) -> Dict[str, str]:
        """Returns fresh train headers with distinct device/request UUIDs."""
        return {
            "Accept": "*/*",
            "ApiKey": self.TRAIN_API_KEY,
            "ClientId": self.TRAIN_CLIENT_ID,
            "AppVersion": "200",
            "DeviceId": uuid.uuid4().hex,
            "Uuid": uuid.uuid4().hex,
            "IxiSrc": "iximweb",
            "Referer": "https://www.ixigo.com/",
            "Origin": "https://www.ixigo.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def get_schedule_headers(self, train_no: str) -> Dict[str, str]:
        """Returns standard browser headers for train schedule requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.redbus.in/railways/trainScheduleDetails?trainNo={train_no}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def get_schedule_cookies(self) -> Dict[str, str]:
        """Returns minimal required session cookies for schedule endpoint."""
        return {
            "country": "IND",
            "currency": "INR",
            "channel": "MWEB",
            "sessionUserType": "GUEST",
        }

    # Backward compatibility properties for existing modules
    @property
    def STATION_HEADERS(self) -> Dict[str, str]:
        return self.get_station_headers()

    @property
    def TRAIN_HEADERS(self) -> Dict[str, str]:
        return self.get_train_headers()


config = IxigoConfig()
