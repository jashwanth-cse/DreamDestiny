"""
Tests for IRCTC Blackout Window Guard (Maintenance & Tatkal hours).
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.services.blackout_guard import check_blackout_window
from app.config import settings

TZ = ZoneInfo("Asia/Kolkata")


def make_ist_dt(hour: int, minute: int, second: int = 0) -> datetime:
    """Helper to create a timezone-aware datetime in Asia/Kolkata."""
    return datetime(2026, 10, 21, hour, minute, second, tzinfo=TZ)


def test_maintenance_window_before_midnight():
    # 23:45 IST falls in 23:40 - 00:25
    dt = make_ist_dt(23, 45)
    is_blocked, reason = check_blackout_window(dt)
    assert is_blocked is True
    assert "Maintenance" in reason


def test_maintenance_window_after_midnight():
    # 00:15 IST falls in 23:40 - 00:25
    dt = make_ist_dt(0, 15)
    is_blocked, reason = check_blackout_window(dt)
    assert is_blocked is True
    assert "Maintenance" in reason


def test_maintenance_window_boundaries():
    # 23:39 IST (1 min before start) -> NOT blocked
    dt_before = make_ist_dt(23, 39)
    is_blocked, _ = check_blackout_window(dt_before)
    assert is_blocked is False

    # 00:25 IST (exact end time) -> NOT blocked
    dt_after = make_ist_dt(0, 25)
    is_blocked, _ = check_blackout_window(dt_after)
    assert is_blocked is False


def test_ac_tatkal_window():
    # 09:45 to 10:15 IST
    dt_inside = make_ist_dt(10, 0)
    is_blocked, reason = check_blackout_window(dt_inside)
    assert is_blocked is True
    assert "AC Tatkal" in reason

    # Boundary checks
    dt_before = make_ist_dt(9, 44, 59)
    assert check_blackout_window(dt_before)[0] is False

    dt_start = make_ist_dt(9, 45, 0)
    assert check_blackout_window(dt_start)[0] is True

    dt_end = make_ist_dt(10, 15, 0)
    assert check_blackout_window(dt_end)[0] is False


def test_sleeper_tatkal_window():
    # 10:45 to 11:15 IST
    dt_inside = make_ist_dt(11, 0)
    is_blocked, reason = check_blackout_window(dt_inside)
    assert is_blocked is True
    assert "Sleeper Tatkal" in reason

    # Boundary checks
    dt_before = make_ist_dt(10, 44, 59)
    assert check_blackout_window(dt_before)[0] is False

    dt_start = make_ist_dt(10, 45, 0)
    assert check_blackout_window(dt_start)[0] is True

    dt_end = make_ist_dt(11, 15, 0)
    assert check_blackout_window(dt_end)[0] is False


def test_normal_operating_hours():
    # 14:30 IST is outside all blackout windows
    dt_normal = make_ist_dt(14, 30)
    is_blocked, reason = check_blackout_window(dt_normal)
    assert is_blocked is False
    assert reason is None


def test_api_run_skipped_during_blackout(client: TestClient):
    """
    Verifies that calling POST /run during a blackout window returns 200 with skipped=True
    so Cloud Scheduler records the execution cleanly without retrying.
    """
    tatkal_dt = make_ist_dt(10, 5)  # 10:05 AM IST (AC Tatkal)
    with patch("app.services.blackout_guard.get_current_ist_time", return_value=tatkal_dt):
        response = client.post("/run", json={"scenario": "balanced"})
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] is True
        assert "Tatkal" in data["reason"]
        assert "safely skipped" in data["message"]
