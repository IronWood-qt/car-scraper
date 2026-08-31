"""Regression tests for storage edge cases found in review."""

import tempfile
from pathlib import Path

from src.car_scraper.storage import SimplifiedListingsStorage


def _storage():
    return SimplifiedListingsStorage(str(Path(tempfile.mkdtemp()) / "data"))


def test_none_price_does_not_crash():
    """A listing with price=None must be skipped, not raise TypeError."""
    storage = _storage()
    listings = [
        {"id": "a", "title": "Good", "price": 100000, "year": 2020},
        {"id": "b", "title": "Bad", "price": None, "year": 2020},
    ]
    summary = storage.store_listings_data("m", listings, "2025-01-01")
    assert summary["total"] == 1  # only the valid one stored
    assert len(summary["new"]) == 1


def test_stable_price_rescrape_grows_history():
    """Re-scraping an unchanged price must still add a reading (a flat line
    on the price-over-time chart, not silence past the very first scrape) -
    not just avoid leaving price_readings empty."""
    storage = _storage()
    listings = [{"id": "a", "title": "Car", "price": 100000, "year": 2020}]
    storage.store_listings_data("m", listings, "2025-01-01")
    # Same price again the next day, and the day after.
    storage.store_listings_data("m", listings, "2025-01-02")
    storage.store_listings_data("m", listings, "2025-01-03")
    df = storage.get_historical_data("m")
    assert len(df) == 3  # one row per scrape, all at the same price
    assert (df["price"] == 100000).all()


def test_new_then_price_drop_reported():
    """A price drop on an existing listing is reported in the summary."""
    storage = _storage()
    storage.store_listings_data(
        "m", [{"id": "a", "title": "Car", "price": 100000, "year": 2020}], "2025-01-01"
    )
    summary = storage.store_listings_data(
        "m", [{"id": "a", "title": "Car", "price": 90000, "year": 2020}], "2025-01-02"
    )
    assert len(summary["price_drops"]) == 1
    assert summary["price_drops"][0]["new_price"] == 90000
