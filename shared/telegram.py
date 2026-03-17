"""
Shared Telegram utilities.

Usage:
    from shared.telegram import TelegramClient

    tg = TelegramClient.from_env()
    tg.send("Hello!")

    # Natural-language command parsing (requires ANTHROPIC_API_KEY in env):
    intent = tg.parse_intent("I booked April 8th")
    # → {"action": "booked", "date": "2026-04-08"}
"""

import json
import os
from datetime import date

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

    # ── Claude intent parsing ──────────────────────────────────────────────────

    def parse_intent(self, message_text: str) -> dict:
        """
        Use Claude to parse a natural-language message into a structured command.

        Returns:
            {"action": "booked" | "unbooked" | "status" | "unknown",
             "date":   "YYYY-MM-DD" | None}

        Requires ANTHROPIC_API_KEY in the environment.
        Falls back to {"action": "unknown", "date": None} on any error.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("  ANTHROPIC_API_KEY not set — Claude parsing unavailable.")
            return {"action": "unknown", "date": None}

        import anthropic

        today = date.today().isoformat()
        system = f"""You parse messages about venue/court bookings into structured commands.
Today is {today}.

Respond with ONLY a JSON object, no explanation:
{{"action": "booked" | "unbooked" | "status" | "unknown", "date": "YYYY-MM-DD" | null}}

Rules:
- "booked"  : user says they reserved or booked a specific date
- "unbooked": user says a booking was cancelled or they're free again on a date
- "status"  : user wants to see current availability
- "unknown" : message doesn't relate to bookings

Resolve relative dates ("next Wednesday", "the 8th", "this weekend") to YYYY-MM-DD.
Use null for date when the action is "status" or "unknown"."""

        try:
            client   = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 80,
                system     = system,
                messages   = [{"role": "user", "content": message_text}],
            )
            return json.loads(response.content[0].text)
        except Exception as e:
            print(f"  Claude parse failed: {e}")
            return {"action": "unknown", "date": None}
