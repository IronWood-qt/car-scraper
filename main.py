#!/usr/bin/env python3
"""Car Scraper - scrape-all engine.

Everything else (browsing listings, managing targets, settings) lives in the
dashboard now - see dashboard/. This is the one thing invoked programmatically
(by the docker-compose 'scraper' loop, or your own cron/systemd) rather than
through a UI, so it stays a CLI rather than moving into the dashboard too.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.car_scraper.scrapers import CarScraper
from src.car_scraper.utils.logger import setup_logger


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="targets.db path (default: $TARGETS_DB or ./targets.db)",
)
@click.option("--data-dir", default="./data", help="Directory to save data")
@click.option(
    "--max-pages",
    default=None,
    type=int,
    help="Override the Settings page's 'Max pages per target' value",
)
@click.option(
    "--alerts-file",
    default="data/alerts.md",
    help="Where to write the alert body (only if there is something to report)",
)
def scrape_all(
    verbose: bool,
    db_path: str | None,
    data_dir: str,
    max_pages: int | None,
    alerts_file: str,
):
    """Scrape every target in targets.db and write an alert summary.

    Each target has its own filtered otomoto/autoplac URL so we only track
    the exact variants we care about (see a target's Settings tab in the
    dashboard).
    """
    setup_logger(log_level="DEBUG" if verbose else "INFO")

    from src.car_scraper.notifiers.pushover import send_pushover
    from src.car_scraper.reporting import format_alert_markdown, format_alert_pushover
    from src.car_scraper.storage.simplified_listings import SimplifiedListingsStorage
    from src.settings_store import SettingsStore
    from src.target_store import open_default_store

    settings = SettingsStore(db_path)
    if max_pages is None:
        max_pages = settings.get("max_pages")

    targets = open_default_store(db_path).list_targets()
    storage = SimplifiedListingsStorage(data_dir)
    current_date = datetime.now().strftime("%Y-%m-%d")

    all_new, all_drops = [], []
    for target in targets:
        key = target["key"]
        label = target.get("label", key)
        # A target may pull from several marketplaces; merge them into one file.
        sources = target.get("sources") or [{"url": target["url"]}]
        click.echo(f"\n=== {label} ===")
        make, _, model = key.partition("-")
        scraper = CarScraper(data_dir, make, model)
        listings: list[dict] = []
        for src in sources:
            try:
                scraper.scrape_model(src["url"], key, max_pages)
                listings.extend(scraper.listings)
            except Exception as e:  # noqa: BLE001 - keep going on per-source failure
                logger.error(f"Source for {key} failed: {e}")
                click.echo(f"  ⚠️  source failed: {e}")
        if not listings:
            click.echo(f"  ⚠️  no listings collected for {key}")
            continue
        try:
            result = storage.store_listings_data(key, listings, current_date)
            for item in result["new"]:
                item["_model_label"] = label
            for drop in result["price_drops"]:
                drop["listing"]["_model_label"] = label
            all_new.extend(result["new"])
            all_drops.extend(result["price_drops"])
            click.echo(
                f"  {result['total']} tracked, {len(result['new'])} new, "
                f"{len(result['price_drops'])} price drops"
            )
        except Exception as e:  # noqa: BLE001 - keep going on per-target failure
            logger.error(f"Storing {key} failed: {e}")
            click.echo(f"  ⚠️  {key} failed: {e}")

    alerts_path = Path(alerts_file)
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    if all_new or all_drops:
        body = format_alert_markdown(all_new, all_drops, current_date)
        alerts_path.write_text(body, encoding="utf-8")
        click.echo(
            f"\n📣 {len(all_new)} new, {len(all_drops)} price drops → {alerts_file}"
        )
        title, message = format_alert_pushover(all_new, all_drops, current_date)
        pushover_token = settings.get("pushover_token") or os.environ.get(
            "PUSHOVER_TOKEN"
        )
        pushover_user = settings.get("pushover_user") or os.environ.get("PUSHOVER_USER")
        dashboard_url = settings.get("dashboard_url") or os.environ.get("DASHBOARD_URL")
        if send_pushover(
            title,
            message,
            token=pushover_token,
            user=pushover_user,
            url=dashboard_url,
            url_title="Open dashboard",
        ):
            click.echo("🔔 Pushover notification sent")
    else:
        # No stale alert file lingering for the pipeline to act on.
        alerts_path.unlink(missing_ok=True)
        click.echo("\n✅ No new cars or price drops")


if __name__ == "__main__":
    scrape_all()
