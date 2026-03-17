"""
Shared Telegram utilities.

Usage:
    from shared.telegram import TelegramClient

    tg = TelegramClient.from_env()
    tg.send("Hello!")

    intent = tg.parse_intent("I booked April 8th")
    # → {"action": "booked", "date": "2026-04-08"}
"""

import os
import re
from datetime import date, datetime, timedelta

import requests


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = str(chat_id)

    @classmethod
    def from_env(cls) -> "TelegramClient":
        token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        return cls(token, chat_id)

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    # ── outbound ───────────────────────────────────────────────────────────────

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message. Returns True on success."""
        if not self.configured:
            print("  Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing).")
            return False
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            r.raise_for_status()
            print("  Telegram sent ✓")
            return True
        except Exception as e:
            print(f"  Telegram failed: {e}")
            return False

    # ── inbound ────────────────────────────────────────────────────────────────

    def get_updates(self, offset: int = 0) -> list[dict]:
        """
        Fetch new updates via long-polling.
        Only returns messages from the authorised chat_id — all others are
        silently dropped so they never reach Claude or any downstream logic.
        """
        if not self.configured:
            return []
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                params={"offset": offset, "timeout": 0},
                timeout=10,
            )
            r.raise_for_status()
            updates = r.json().get("result", [])
        except Exception as e:
            print(f"  getUpdates failed: {e}")
            return []

        # Security: only pass through messages from our own chat
        authorised = []
        for upd in updates:
            msg_chat = str(upd.get("message", {}).get("chat", {}).get("id", ""))
            if msg_chat == self.chat_id:
                authorised.append(upd)
        return authorised

    # ── Intent parsing ─────────────────────────────────────────────────────────

    def parse_intent(self, message_text: str) -> dict:
        """
        Parse a natural-language booking message using keyword + date matching.

        Returns:
            {"action": "booked" | "unbooked" | "status" | "unknown",
             "date":   "YYYY-MM-DD" | None}
        """
        text = message_text.lower().strip()

        action = _detect_action(text)
        if action == "unknown":
            return {"action": "unknown", "date": None}

        parsed_date = _extract_date(message_text) if action in ("booked", "unbooked") else None
        return {"action": action, "date": parsed_date}


# ── Intent helpers (module-level so they're easy to unit-test) ─────────────────

_BOOKED_KEYWORDS = [
    "booked", "reserved", "confirmed", "secured",
    "got a court", "got the court", "we got", "i got",
    "locked in", "sorted",
]

_UNBOOKED_KEYWORDS = [
    "cancelled", "canceled", "can't make", "cant make", "cannot make",
    "won't make", "wont make", "free again", "no longer", "not going",
    "remove", "unbook", "fell through", "not happening",
]

_STATUS_KEYWORDS = [
    "available", "availability", "any slots", "open slots",
    "what's free", "whats free", "what is free",
    "check", "status", "what do we have", "show me",
    "what's open", "whats open",
]


def _detect_action(text: str) -> str:
    if any(kw in text for kw in _UNBOOKED_KEYWORDS):
        return "unbooked"
    if any(kw in text for kw in _BOOKED_KEYWORDS):
        return "booked"
    if any(kw in text for kw in _STATUS_KEYWORDS):
        return "status"
    return "unknown"


def _extract_date(text: str) -> str | None:
    """
    Extract a date from natural language text and return it as YYYY-MM-DD.
    Handles:
      - ISO dates:            "2026-04-08"
      - Month + day:          "April 8th", "Mar 25", "the 8th"
      - Relative weekdays:    "next Wednesday", "this Wednesday"
      - "next week":          the coming Wednesday
    Returns None if no date can be parsed.
    """
    today = date.today()

    # ISO date
    m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if m:
        return m.group(1)

    # "next Wednesday" / "this Wednesday"
    m = re.search(r'\b(next|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
                  text, re.IGNORECASE)
    if m:
        target = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].index(
            m.group(2).lower()
        )
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0 or m.group(1).lower() == "next":
            days_ahead = days_ahead or 7
        return (today + timedelta(days=days_ahead)).isoformat()

    # Month name + day number ("April 8th", "Apr 8", "March 25")
    m = re.search(
        r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?'
        r'|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
        r'\s+(\d{1,2})(?:st|nd|rd|th)?\b',
        text, re.IGNORECASE,
    )
    if m:
        try:
            from dateutil import parser as dp
            parsed = dp.parse(f"{m.group(1)} {m.group(2)}", default=datetime(today.year, 1, 1))
            # If the date has already passed this year, assume next year
            if parsed.date() < today:
                parsed = dp.parse(f"{m.group(1)} {m.group(2)}", default=datetime(today.year + 1, 1, 1))
            return parsed.date().isoformat()
        except Exception:
            pass

    # Bare ordinal: "the 8th", "on the 25th" — assume nearest future occurrence
    m = re.search(r'\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        try:
            candidate = today.replace(day=day)
            if candidate < today:
                # roll forward one month
                month = today.month % 12 + 1
                year  = today.year + (1 if today.month == 12 else 0)
                candidate = candidate.replace(year=year, month=month)
            return candidate.isoformat()
        except ValueError:
            pass

    return None
