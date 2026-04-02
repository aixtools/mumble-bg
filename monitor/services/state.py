from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..models import MonitorState


def load_state(path: str | Path) -> MonitorState:
    """
    Load the monitor state from JSON.

    Returns a default state when the file does not exist.
    """
    state_path = Path(path)
    if not state_path.exists():
        return MonitorState()
    with state_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return MonitorState.from_dict(payload)


def save_state(path: str | Path, state: MonitorState) -> None:
    """
    Persist monitor state to JSON atomically.

    Writes to a temporary file before replacing the target.
    """
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(state_path)


def update_known_users(state: MonitorState, users: Iterable[str]) -> None:
    """
    Update the state with the latest known usernames.
    """
    state.known_users = set(users)
