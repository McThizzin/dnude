"""Persisted user-level TUI preferences (currently: theme).

Stored under ~/.config/dnude/ rather than the project directory, so the
choice follows the user across whatever directory they happen to run
`dnude` from, the same way most terminal tools handle preferences.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_DIR = Path.home() / ".config" / "dnude"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def load_theme(default: str) -> str:
    """Return the last-saved theme name, or `default` if none is stored."""
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return default

    theme = data.get("theme")
    return theme if isinstance(theme, str) else default


def save_theme(theme: str) -> None:
    """Persist the chosen theme. Failures are swallowed — a missing/
    unwritable config dir shouldn't crash the app, just means the
    preference won't stick.
    """
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump({"theme": theme}, f)
    except OSError:
        pass
