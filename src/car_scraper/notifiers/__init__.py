"""Push notification channels for the daily pipeline."""

from src.car_scraper.notifiers.pushover import send_pushover

__all__ = ["send_pushover"]
