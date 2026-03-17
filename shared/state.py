"""
Shared JSON state file utilities.

Usage:
    from shared.state import StateManager

    sm    = StateManager(Path("my_state.json"), defaults={"checks": [], "alerted": []})
    state = sm.load()
    sm.append_and_prune(state, "checks", {"checked_at": now, ...}, max_kept=100)
    sm.save(state)
"""

import json
from pathlib import Path
from typing import Any


class StateManager:
    def __init__(self, file_path: Path, defaults: dict | None = None):
        self.file_path = file_path
        self.defaults  = defaults or {}

    def load(self) -> dict:
        if self.file_path.exists():
            return json.loads(self.file_path.read_text())
        return self.defaults.copy()

    def save(self, state: dict) -> None:
        self.file_path.write_text(json.dumps(state, indent=2))

    def append_and_prune(
        self, state: dict, key: str, record: Any, max_kept: int = 100
    ) -> None:
        """Append a record to state[key] list, keeping only the last max_kept entries."""
        state.setdefault(key, []).append(record)
        state[key] = state[key][-max_kept:]
