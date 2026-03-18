"""
Google Calendar iCal reader.

Fetches events from a private iCal URL (no OAuth or API key required).
The URL is read from the GOOGLE_ICAL_URL environment variable — never
hardcoded so it stays out of source control.

Usage:
    from shared.google_calendar import fetch_bkbc_bookings

    bookings = fetch_bkbc_bookings()
    # → [{"date": "2026-04-01", "summary": "...", "court": "5", "time": "8:30 PM"}, ...]
"""

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar

ET = ZoneInfo("America/New_York")

# Keywords that identify a BKBC booking event
_BKBC_KEYWORDS = ["brooklyn badminton", "bkbc", "14 woodward"]


def _is_bkbc_event(summary: str, location: str) -> bool:
    text = f"{summary} {location}".lower()
    return any(kw in text for kw in _BKBC_KEYWORDS)


def _extract_court(summary: str) -> str | None:
    """Extract court number from event title, e.g. 'BKBC - court #5' → '5'."""
    m = re.search(r"court\s*#?(\d+)", summary, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_time(summary: str) -> str | None:
    """Extract booking size hint, e.g. '8ppl' → '8 people'."""
    m = re.search(r"(\d+)\s*ppl", summary, re.IGNORECASE)
    return f"{m.group(1)} people" if m else None


def fetch_bkbc_bookings(from_date: date | None = None) -> list[dict]:
    """
    Fetch upcoming BKBC court bookings from the private iCal feed.

    Args:
        from_date: only return events on or after this date (defaults to today)

    Returns:
        List of dicts sorted by date:
        [{"date": "YYYY-MM-DD", "court": "5", "size": "8 people",
          "summary": "...", "start_dt": datetime}, ...]

    Security: the iCal URL is read from GOOGLE_ICAL_URL env var and never
    logged or exposed in output.
    """
    url = os.getenv("GOOGLE_ICAL_URL", "")
    if not url:
        return []

    cutoff = from_date or date.today()

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        cal = Calendar.from_ical(r.content)
    except Exception as e:
        print(f"  Calendar fetch failed: {e}")
        return []

    bookings = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary  = str(component.get("SUMMARY", ""))
        location = str(component.get("LOCATION", ""))

        if not _is_bkbc_event(summary, location):
            continue

        dtstart = component.get("DTSTART").dt
        if isinstance(dtstart, datetime):
            dtstart_et = dtstart.astimezone(ET)
            event_date = dtstart_et.date()
            time_display = dtstart_et.strftime("%-I:%M %p")
        else:
            event_date   = dtstart
            time_display = None

        if event_date < cutoff:
            continue

        bookings.append({
            "date":         event_date.isoformat(),
            "court":        _extract_court(summary),
            "size":         _extract_time(summary),
            "time":         time_display,
            "summary":      summary,
        })

    bookings.sort(key=lambda b: b["date"])
    return bookings


def booked_dates_from_calendar() -> set[str]:
    """Return the set of dates that already have a BKBC booking."""
    return {b["date"] for b in fetch_bkbc_bookings()}
