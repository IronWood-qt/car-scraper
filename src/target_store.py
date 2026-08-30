"""SQLite-backed target configuration store.

Replaces targets.json as the editable source of truth for which cars are
tracked (and their per-target "facets" classification rules): same private-
by-default treatment (see .gitignore - targets.db is never committed, in
this repo or a fork), but editable through the dashboard's "Manage Targets"
page instead of hand-editing JSON.

Deliberately dependency-free (stdlib only: sqlite3/json/pathlib) and outside
the car_scraper package (car_scraper/__init__.py eagerly imports httpx,
pydantic, matplotlib, ...) so the standalone dashboard container can import
this one module without any of that - see dashboard/Dockerfile.
"""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "targets.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    note TEXT,
    sources_json TEXT NOT NULL,
    facets_json TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class TargetStoreError(ValueError):
    """Invalid target data (bad key, unparseable sources/facets JSON, ...)."""


def _row_to_target(row: sqlite3.Row) -> dict[str, Any]:
    target = {
        "key": row["key"],
        "label": row["label"],
        "sources": json.loads(row["sources_json"]),
    }
    if row["note"]:
        target["note"] = row["note"]
    if row["facets_json"]:
        target["facets"] = json.loads(row["facets_json"])
    return target


def _validate_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        raise TargetStoreError("key is required")
    if not all(c.isalnum() or c == "-" for c in key):
        raise TargetStoreError(
            f"key {key!r} must be lowercase letters/digits/hyphens (e.g. 'make-model')"
        )
    return key


def _validate_sources(sources: list[dict]) -> list[dict]:
    if not isinstance(sources, list) or not sources:
        raise TargetStoreError("sources must be a non-empty list")
    for s in sources:
        if not isinstance(s, dict) or not s.get("url"):
            raise TargetStoreError(f"each source needs a 'url': {s!r}")
    return sources


def _validate_facets(facets: dict | None) -> dict | None:
    if not facets:
        return None
    if not isinstance(facets, dict):
        raise TargetStoreError("facets must be an object")
    for dimension, rules in facets.items():
        if dimension not in ("variant", "trim", "body"):
            raise TargetStoreError(
                f"facets.{dimension}: unknown dimension (use variant/trim/body)"
            )
        if not isinstance(rules, list):
            raise TargetStoreError(f"facets.{dimension} must be a list of rules")
        for rule in rules:
            if (
                not isinstance(rule, dict)
                or not rule.get("label")
                or not rule.get("keywords")
            ):
                raise TargetStoreError(
                    f"facets.{dimension}: each rule needs 'label' and 'keywords': {rule!r}"
                )
    return facets


class TargetStore:
    """CRUD over the targets table. One instance per db_path is cheap to make."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or os.environ.get("TARGETS_DB", DEFAULT_DB_PATH))
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_targets(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM targets ORDER BY sort_order, key"
            ).fetchall()
        return [_row_to_target(r) for r in rows]

    def get(self, key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM targets WHERE key = ?", (key,)).fetchone()
        return _row_to_target(row) if row else None

    def upsert(
        self,
        key: str,
        label: str,
        sources: list[dict],
        note: str | None = None,
        facets: dict | None = None,
        sort_order: int = 0,
    ) -> None:
        """Insert or fully replace one target. Raises TargetStoreError on bad input."""
        key = _validate_key(key)
        label = (label or key).strip()
        sources = _validate_sources(sources)
        facets = _validate_facets(facets)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO targets (key, label, note, sources_json, facets_json, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    label = excluded.label,
                    note = excluded.note,
                    sources_json = excluded.sources_json,
                    facets_json = excluded.facets_json,
                    sort_order = excluded.sort_order,
                    updated_at = datetime('now')
                """,
                (
                    key,
                    label,
                    note or None,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(facets, ensure_ascii=False) if facets else None,
                    sort_order,
                ),
            )
            conn.commit()

    def delete(self, key: str) -> bool:
        """Returns True if a row was deleted."""
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM targets WHERE key = ?", (key,))
            conn.commit()
        return cur.rowcount > 0

    def import_json(self, path: str | Path, *, overwrite: bool = False) -> int:
        """Import targets from a targets.json-shaped file. Returns count imported.

        Existing keys are skipped unless ``overwrite=True`` (used for the
        one-time auto-migration from a pre-database targets.json, and for
        manually re-seeding from targets.example.json).
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        existing = {t["key"] for t in self.list_targets()}
        count = 0
        for i, t in enumerate(data.get("targets", [])):
            key = t.get("key")
            if not key or (key in existing and not overwrite):
                continue
            self.upsert(
                key=key,
                label=t.get("label", key),
                sources=t.get("sources")
                or ([{"url": t["url"]}] if t.get("url") else []),
                note=t.get("note"),
                facets=t.get("facets"),
                sort_order=i,
            )
            count += 1
        return count

    def export_json(self, path: str | Path) -> None:
        """Write the current targets out in the same shape as targets.json (backup/inspection)."""
        payload = {"targets": self.list_targets()}
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def open_default_store(
    db_path: str | Path | None = None, seed_from: str | Path = "targets.json"
) -> TargetStore:
    """Open the store, auto-importing from ``seed_from`` the first time it's created.

    Lets an existing targets.json-based setup upgrade transparently: if
    targets.db doesn't exist yet but targets.json does, its contents become
    the initial rows. A no-op on every later call (targets.db already exists).
    """
    resolved = Path(db_path or os.environ.get("TARGETS_DB", DEFAULT_DB_PATH))
    is_new = not resolved.exists()
    store = TargetStore(resolved)
    if is_new and Path(seed_from).exists():
        store.import_json(seed_from)
    return store
