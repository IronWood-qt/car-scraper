"""Unit tests for src/facets.py's condition (accident/damage) detection.

Country/variant/trim/config-engine coverage lives in facets.py's own
_selfcheck() (run via `python -m src.facets`); these tests focus on the
accident_free/damaged fields since they're new and worth pinning down.
"""

import pytest

from src.facets import classify


def _condition(title="", short_description=""):
    result = classify(
        "some-model", {"title": title, "short_description": short_description}
    )
    return result["accident_free"], result["damaged"]


@pytest.mark.parametrize(
    "text",
    ["Bezwypadkowy!", "bezwypadkowa, serwisowana", "BEZWYPADKOWY, pierwszy właściciel"],
)
def test_accident_free_marker_detected(text):
    accident_free, damaged = _condition(short_description=text)
    assert accident_free is True
    assert damaged is None  # bezwypadkowy alone says nothing about damage


@pytest.mark.parametrize(
    "text", ["Auto powypadkowe", "Po wypadku, sprzedam", "Kolizja z tyłu"]
)
def test_had_accident_marker_sets_accident_free_false_and_damaged_true(text):
    accident_free, damaged = _condition(short_description=text)
    assert accident_free is False
    assert damaged is True  # powypadkowy/kolizja implies damage


@pytest.mark.parametrize(
    "text", ["Uszkodzony zderzak", "do naprawy blacharka", "Rozbity przód, na części"]
)
def test_damage_marker_without_accident_word(text):
    accident_free, damaged = _condition(short_description=text)
    assert accident_free is None  # not explicitly an accident, just damage
    assert damaged is True


def test_nothing_mentioned_is_unknown_not_false():
    accident_free, damaged = _condition(title="Toyota Corolla 1.6 Comfort")
    assert accident_free is None
    assert damaged is None


def test_diacritics_are_folded():
    """'uszkodzenia' with real Polish diacritics elsewhere in the sentence."""
    accident_free, damaged = _condition(
        short_description="Drobne uszkodzenia lakieru, poza tym bez zarzutu"
    )
    assert damaged is True


def test_always_present_in_classify_output():
    """Every listing gets both keys, even with no config/hardcoded classifier."""
    result = classify("unknown-model", {"title": "Whatever"})
    assert "accident_free" in result
    assert "damaged" in result
