"""
IRCTC Blackout Window Guard.

Protects against triggering load tests during high-risk IRCTC operational windows:
  1. IRCTC Server Maintenance:        11:40 PM - 12:25 AM IST (23:40 - 00:25)
  2. AC Tatkal Opening Window:        09:45 AM - 10:15 AM IST (High rate limits)
  3. Non-AC / Sleeper Tatkal Window:  10:45 AM - 11:15 AM IST (High rate limits)
"""

from datetime import datetime, time as dt_time
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from app.config import settings

# Defined blackout intervals in Asia/Kolkata (IST) time
MAINTENANCE_START = dt_time(23, 40)
MAINTENANCE_END = dt_time(0, 25)

AC_TATKAL_START = dt_time(9, 45)
AC_TATKAL_END = dt_time(10, 15)

SLEEPER_TATKAL_START = dt_time(10, 45)
SLEEPER_TATKAL_END = dt_time(11, 15)


def get_current_ist_time() -> datetime:
    """Returns the current datetime in the configured timezone (Asia/Kolkata)."""
    try:
        tz = ZoneInfo(settings.timezone)
        return datetime.now(tz)
    except Exception:
        # Fallback to local system time if zoneinfo fails
        return datetime.now()


def is_in_time_range(t: dt_time, start: dt_time, end: dt_time) -> bool:
    """
    Checks if a time t falls between start and end.
    Correctly handles intervals that cross midnight (e.g. 23:40 to 00:25).
    """
    if start <= end:
        return start <= t < end
    else:
        # Over midnight: e.g. 23:40 to 00:25
        return t >= start or t < end


def check_blackout_window(check_dt: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether the given datetime (or current IST time) falls in an IRCTC blackout window.

    Returns:
        (is_blackout: bool, reason: Optional[str])
    """
    if not settings.enforce_blackout_windows:
        return False, None

    dt = check_dt or get_current_ist_time()
    t = dt.time()

    # 1. IRCTC Maintenance Window: 11:40 PM to 12:25 AM
    if is_in_time_range(t, MAINTENANCE_START, MAINTENANCE_END):
        return (
            True,
            f"IRCTC Daily Server Maintenance Window (11:40 PM - 12:25 AM IST). "
            f"Current time: {dt.strftime('%H:%M:%S IST')}."
        )

    # 2. AC Tatkal Opening Window: 9:45 AM to 10:15 AM
    if is_in_time_range(t, AC_TATKAL_START, AC_TATKAL_END):
        return (
            True,
            f"AC Tatkal Booking Opening Window (09:45 AM - 10:15 AM IST) — strict rate limits enforced. "
            f"Current time: {dt.strftime('%H:%M:%S IST')}."
        )

    # 3. Non-AC / Sleeper Tatkal Window: 10:45 AM to 11:15 AM
    if is_in_time_range(t, SLEEPER_TATKAL_START, SLEEPER_TATKAL_END):
        return (
            True,
            f"Non-AC/Sleeper Tatkal Booking Opening Window (10:45 AM - 11:15 AM IST) — strict rate limits enforced. "
            f"Current time: {dt.strftime('%H:%M:%S IST')}."
        )

    return False, None
