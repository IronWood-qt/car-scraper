"""Unit tests for the SQLite-backed target store."""

import json
import tempfile
from pathlib import Path

import pytest

from src.target_store import TargetStore, TargetStoreError, open_default_store


def _store() -> TargetStore:
    return TargetStore(Path(tempfile.mkdtemp()) / "targets.db")


def test_empty_store_lists_nothing():
    assert _store().list_targets() == []


def test_upsert_then_get_round_trips():
    store = _store()
    store.upsert(
        key="toyota-gr86",
        label="Toyota GR86",
        sources=[{"site": "otomoto", "url": "https://example.com/gr86"}],
        note="manual only",
    )
    t = store.get("toyota-gr86")
    assert t["label"] == "Toyota GR86"
    assert t["sources"] == [{"site": "otomoto", "url": "https://example.com/gr86"}]
    assert t["note"] == "manual only"
    assert "facets" not in t  # omitted, not null, when unset


def test_upsert_with_facets_round_trips():
    store = _store()
    facets = {"variant": [{"label": "T8", "keywords": ["t8", "recharge"]}]}
    store.upsert("volvo-xc90", "Volvo XC90", sources=[{"url": "u"}], facets=facets)
    assert store.get("volvo-xc90")["facets"] == facets


def test_upsert_is_idempotent_update():
    store = _store()
    store.upsert("k", "Label 1", sources=[{"url": "u"}])
    store.upsert("k", "Label 2", sources=[{"url": "u2"}])
    targets = store.list_targets()
    assert len(targets) == 1
    assert targets[0]["label"] == "Label 2"
    assert targets[0]["sources"] == [{"url": "u2"}]


def test_get_missing_key_returns_none():
    assert _store().get("nope") is None


def test_delete_returns_whether_a_row_was_removed():
    store = _store()
    store.upsert("k", "Label", sources=[{"url": "u"}])
    assert store.delete("k") is True
    assert store.delete("k") is False
    assert store.list_targets() == []


@pytest.mark.parametrize(
    "kwargs,message_part",
    [
        ({"key": "", "label": "x", "sources": [{"url": "u"}]}, "key is required"),
        (
            {"key": "Bad Key!", "label": "x", "sources": [{"url": "u"}]},
            "lowercase letters",
        ),
        ({"key": "k", "label": "x", "sources": []}, "non-empty list"),
        ({"key": "k", "label": "x", "sources": [{"site": "otomoto"}]}, "needs a 'url'"),
        (
            {
                "key": "k",
                "label": "x",
                "sources": [{"url": "u"}],
                "facets": {"bogus": []},
            },
            "unknown dimension",
        ),
        (
            {
                "key": "k",
                "label": "x",
                "sources": [{"url": "u"}],
                "facets": {"trim": [{"label": "Only label"}]},
            },
            "needs 'label' and 'keywords'",
        ),
    ],
)
def test_upsert_rejects_invalid_input(kwargs, message_part):
    with pytest.raises(TargetStoreError, match=message_part):
        _store().upsert(**kwargs)


def test_import_json_skips_existing_keys_by_default():
    store = _store()
    store.upsert("k", "Original", sources=[{"url": "u"}])
    src = Path(tempfile.mkdtemp()) / "src.json"
    src.write_text(
        json.dumps(
            {"targets": [{"key": "k", "label": "New", "sources": [{"url": "u2"}]}]}
        )
    )
    n = store.import_json(src)
    assert n == 0
    assert store.get("k")["label"] == "Original"


def test_import_json_overwrite_replaces_existing():
    store = _store()
    store.upsert("k", "Original", sources=[{"url": "u"}])
    src = Path(tempfile.mkdtemp()) / "src.json"
    src.write_text(
        json.dumps(
            {"targets": [{"key": "k", "label": "New", "sources": [{"url": "u2"}]}]}
        )
    )
    n = store.import_json(src, overwrite=True)
    assert n == 1
    assert store.get("k")["label"] == "New"


def test_import_json_handles_bare_url_shape():
    """Older targets.json entries used a top-level "url" instead of "sources"."""
    store = _store()
    src = Path(tempfile.mkdtemp()) / "src.json"
    src.write_text(json.dumps({"targets": [{"key": "k", "label": "L", "url": "u"}]}))
    store.import_json(src)
    assert store.get("k")["sources"] == [{"url": "u"}]


def test_export_then_import_round_trips(tmp_path):
    store = _store()
    store.upsert(
        "k",
        "Label",
        sources=[{"url": "u"}],
        facets={"trim": [{"label": "X", "keywords": ["x"]}]},
    )
    out = tmp_path / "export.json"
    store.export_json(out)

    store2 = _store()
    store2.import_json(out)
    assert store2.get("k") == store.get("k")


def test_open_default_store_auto_imports_legacy_json_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "targets.json"
    legacy.write_text(
        json.dumps(
            {"targets": [{"key": "a-b", "label": "AB", "sources": [{"url": "u"}]}]}
        )
    )

    db_path = tmp_path / "targets.db"
    store = open_default_store(db_path, seed_from=legacy)
    assert [t["key"] for t in store.list_targets()] == ["a-b"]

    # Manually add a second target, then reopen - must not re-import/duplicate.
    store.upsert("c-d", "CD", sources=[{"url": "u2"}])
    store2 = open_default_store(db_path, seed_from=legacy)
    assert sorted(t["key"] for t in store2.list_targets()) == ["a-b", "c-d"]


def test_open_default_store_without_legacy_json_is_empty(tmp_path):
    db_path = tmp_path / "targets.db"
    store = open_default_store(db_path, seed_from=tmp_path / "nonexistent.json")
    assert store.list_targets() == []
