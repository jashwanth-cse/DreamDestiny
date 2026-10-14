import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_webhook_verification_success():
    """Verify Meta webhook challenge handshake succeeds with valid token."""
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 200
    assert response.text == "1158201444"


def test_webhook_verification_failure():
    """Verify handshake rejected with invalid token."""
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 403


def test_health_and_readiness_probes():
    """Verify health and readiness probes respond with 200 OK."""
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"


def test_webhook_signature_verification(monkeypatch):
    """Verify Meta HMAC-SHA256 signature verification rejects forged payloads and accepts valid ones."""
    import hmac
    import hashlib
    import json

    secret = "test_meta_app_secret_123"
    monkeypatch.setattr(settings, "whatsapp_app_secret", secret)
    monkeypatch.setattr(settings, "app_env", "production")

    payload = {"object": "whatsapp_business_account", "entry": []}
    payload_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature -> 403
    resp_missing = client.post("/webhook", content=payload_bytes, headers={"Content-Type": "application/json"})
    assert resp_missing.status_code == 403
    assert resp_missing.json()["detail"] == "Missing signature"

    # 2. Forged/invalid signature -> 403
    resp_invalid = client.post(
        "/webhook",
        content=payload_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalidhex0000000000000000"}
    )
    assert resp_invalid.status_code == 403
    assert resp_invalid.json()["detail"] == "Invalid signature"

    # 3. Valid signature -> 200
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    resp_valid = client.post(
        "/webhook",
        content=payload_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig}
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json() == {"status": "received"}
