"""
Pytest fixtures and environment setup for TrainWatch Load-Test Service tests.
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure trainwatch-loadtest-service directory is on sys.path
service_root = Path(__file__).resolve().parent.parent
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))

# Force offline/test settings before importing app modules
os.environ["ENABLE_FIRESTORE"] = "false"
os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["TARGET_AVAILABILITY_URL"] = "http://test-server/api/v1/trains/availability"
os.environ["DEFAULT_CONCURRENCY"] = "5"
os.environ["DEFAULT_TOTAL_REQUESTS"] = "10"
os.environ["MAX_ALLOWED_CONCURRENCY"] = "20"
os.environ["MAX_ALLOWED_REQUESTS"] = "50"

from app.main import app
from app.config import settings


@pytest.fixture
def client():
    """Provides a TestClient for FastAPI endpoints."""
    with TestClient(app) as test_client:
        yield test_client
