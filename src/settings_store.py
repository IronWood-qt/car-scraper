"""Simple key-value runtime settings, sharing targets.db (see target_store.py).

Knobs that used to be CLI flags / .env-only (max pages per target, the
scraper container's loop interval, Pushover credentials, the dashboard URL
alerts link to) - editable from the dashboard's Settings page instead, no
restart needed for most of them. Same stdlib-only, outside-car_scraper-
package treatment as target_store.py, for the same reason: the standalone
dashboard container needs to import this without the scraper package's own
(much heavier) dependencies.
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "targets.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# name -> (default, type). Values are always stored as text (SQLite is
# dynamically typed, but keeping storage as str avoids type-drift surprises)
# and cast back on read.
_DEFAULTS: dict[str, tuple[Any, type]] = {
    "max_pages": (10, int),
    "scrape_interval_seconds": (21600, int),  # 6h
    "pushover_token": ("", str),
    "pushover_user": ("", str),
    "dashboard_url": ("", str),
}


class SettingsStore:
    """Get/set typed settings. One instance per db_path is cheap to make."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or os.environ.get("TARGETS_DB", DEFAULT_DB_PATH))
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, key: str) -> Any:
        """Returns the stored value cast to its declared type, or the
        declared default if unset/unparseable. Raises KeyError for an
        unknown setting name (typo-guard, not a general-purpose KV store)."""
        default, caster = _DEFAULTS[key]
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None or row[0] is None or row[0] == "":
            return default
        try:
            return caster(row[0])
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value: Any) -> None:
        if key not in _DEFAULTS:
            raise KeyError(f"unknown setting {key!r}")
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            conn.commit()

    def all(self) -> dict[str, Any]:
        return {key: self.get(key) for key in _DEFAULTS}
