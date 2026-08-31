"""Unit tests for the SQLite-backed settings store."""

import tempfile
from pathlib import Path

import pytest

from src.settings_store import SettingsStore


def _store() -> SettingsStore:
    return SettingsStore(Path(tempfile.mkdtemp()) / "targets.db")


def test_unset_setting_returns_its_default():
    store = _store()
    assert store.get("max_pages") == 10
    assert store.get("scrape_interval_seconds") == 21600
    assert store.get("pushover_token") == ""


def test_set_then_get_round_trips_with_correct_type():
    store = _store()
    store.set("max_pages", 25)
    value = store.get("max_pages")
    assert value == 25
    assert isinstance(value, int)


def test_set_persists_across_instances_of_same_db():
    db_path = Path(tempfile.mkdtemp()) / "targets.db"
    SettingsStore(db_path).set("max_pages", 3)
    assert SettingsStore(db_path).get("max_pages") == 3


def test_string_setting_round_trips():
    store = _store()
    store.set("pushover_token", "abc123")
    assert store.get("pushover_token") == "abc123"


def test_empty_string_reads_back_as_default():
    """Clearing a text field in the UI should mean 'unset', not a literal ''."""
    store = _store()
    store.set("dashboard_url", "http://example.com")
    store.set("dashboard_url", "")
    assert store.get("dashboard_url") == ""  # default for dashboard_url is also ""


def test_unknown_setting_get_raises():
    with pytest.raises(KeyError):
        _store().get("not_a_real_setting")


def test_unknown_setting_set_raises():
    with pytest.raises(KeyError):
        _store().set("not_a_real_setting", "x")


def test_all_returns_every_default_when_nothing_set():
    store = _store()
    assert store.all() == {
        "max_pages": 10,
        "scrape_interval_seconds": 21600,
        "pushover_token": "",
        "pushover_user": "",
        "dashboard_url": "",
    }


def test_all_reflects_updates():
    store = _store()
    store.set("max_pages", 50)
    store.set("pushover_user", "u1")
    result = store.all()
    assert result["max_pages"] == 50
    assert result["pushover_user"] == "u1"
    assert result["scrape_interval_seconds"] == 21600  # untouched, still default
