#!/usr/bin/env python3
"""
Car Scraper CLI
A refactored, modular car scraper for otomoto.pl with comprehensive features.

This application provides:
- Car listing scraping from otomoto.pl
- Individual listing price tracking over time
- Comprehensive data analysis and visualization
- Price change detection and alerts
- Multiple output formats (CSV, JSON)
- Professional logging and error handling
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.car_scraper.plotters import IndividualListingsPlotter, YearAnalysisPlotter
from src.car_scraper.scrapers import CarScraper
from src.car_scraper.utils.logger import setup_logger


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Set logging level",
)
def cli(verbose: bool, log_level: str):
    """
    🚗 Modern Car Scraper CLI for otomoto.pl

    A professional car listing scraper with price tracking, analysis, and visualization.
    """
    # Setup logging
    level = "DEBUG" if verbose else log_level
    setup_logger(log_level=level)

    logger.info("Car Scraper CLI initialized")
    logger.debug(f"Logging level set to: {level}")


@cli.command()
@click.option("--url", help="Search URL from otomoto.pl (for advanced queries)")
@click.option(
    "--manufacturer", "--make", help="Car manufacturer (e.g., lexus, bmw, audi)"
)
@click.option("--model", help="Car model (e.g., lc, i8, r8)")
@click.option("--data-dir", default="./data", help="Directory to save data")
@click.option("--max-pages", default=10, help="Maximum number of pages to scrape")
@click.option(
    "--format",
    "output_format",
    default="csv",
    type=click.Choice(["csv", "json"]),
    help="Output format",
)
@click.option("--delay", default=1.0, help="Delay between requests (seconds)")
def scrape(
    url: str,
    manufacturer: str,
    model: str,
    data_dir: str,
    max_pages: int,
    output_format: str,
    delay: float,
):
    """
    🔍 Scrape car listings from otomoto.pl

    Extract car listings with prices, specifications, and metadata.
    Automatically tracks individual listings over time for price analysis.

    Two modes:
    1. Simple: --manufacturer lexus --model lc
    2. Advanced: --url "https://www.otomoto.pl/osobowe/lexus/lc?specific=query"

    Examples:
        python main.py scrape --manufacturer lexus --model lc
        python main.py scrape --url "https://www.otomoto.pl/osobowe/bmw/i8"
    """

    # Validate input - must have either URL or manufacturer+model
    if not url and not (manufacturer and model):
        raise click.UsageError(
            "Must provide either --url OR both --manufacturer and --model"
        )

    # Mode 1: Simple mode - generate URL from manufacturer and model
    if manufacturer and model and not url:
        url = f"https://www.otomoto.pl/osobowe/{manufacturer.lower()}/{model.lower()}"
        make = manufacturer.lower()
        car_model = model.lower()
        model_key = f"{make}-{car_model}"
        logger.info("Simple mode: Generated URL from manufacturer and model")

    # Mode 2: Advanced mode - extract from URL, allow overrides
    elif url:
        # Extract manufacturer and model from URL
        import re

        url_parts = re.findall(r"/osobowe/([^/]+)/([^/?]+)", url)
        if url_parts:
            url_make, url_model = url_parts[0]
        else:
            raise click.UsageError(
                "Cannot extract manufacturer/model from URL. "
                "Please provide --manufacturer and --model explicitly."
            )

        # Use provided manufacturer/model or fall back to URL extraction
        make = manufacturer.lower() if manufacturer else url_make.lower()
        car_model = model.lower() if model else url_model.lower()
        model_key = f"{make}-{car_model}"

        if manufacturer or model:
            logger.info("Advanced mode: Using URL with manufacturer/model override")
        else:
            logger.info("Advanced mode: Extracted manufacturer/model from URL")

    logger.info(f"Starting scrape for: {make} {car_model}")
    logger.info(f"URL: {url}")
    logger.info(f"Model key: {model_key}")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Max pages: {max_pages}")
    logger.info(f"Output format: {output_format}")

    try:
        # Initialize scraper with make and model
        scraper = CarScraper(data_dir, make, car_model)

        # Scrape the model
        scraper.scrape_model(url, model_key, max_pages)

        # Initialize simplified listings storage for historical tracking
        from src.car_scraper.storage.simplified_listings import (
            SimplifiedListingsStorage,
        )

        storage = SimplifiedListingsStorage(data_dir)
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Process scraped data with simplified storage
        logger.info(f"Processing listings data for {model_key}")
        click.echo(f"📊 Processing listings data for {model_key}")

        # Store data using simplified storage system
        result = storage.store_listings_data(model_key, scraper.listings, current_date)

        # Log completion
        logger.success("Scraping completed successfully!")
        click.echo(f"✅ Scraping completed for: {make} {car_model}")
        click.echo(
            f"   {result['total']} tracked, {len(result['new'])} new, "
            f"{len(result['price_drops'])} price drops"
        )
        click.echo(f"📁 Data saved to: {data_dir}")

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise click.ClickException(f"Scraping failed: {e}") from e


@cli.command()
@click.option("--model", required=True, help="Model name to generate plots for")
@click.option("--data-dir", default="./data", help="Directory containing data")
@click.option(
    "--plot-type",
    default="all",
    type=click.Choice(["all", "individual", "year"]),
    help="Type of plots to generate",
)
@click.option("--output-dir", default="./plots", help="Directory to save plots")
def plot(model: str, data_dir: str, plot_type: str, output_dir: str):
    """
    📊 Generate visualization plots for scraped data

    Create comprehensive analysis charts including price trends,
    year-based analysis, and individual listing tracking.

    Example:
        python main.py plot --model "bmw-i8" --plot-type "all"
    """
    logger.info(f"Generating {plot_type} plots for model: {model}")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Output directory: {output_dir}")

    try:
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if plot_type in ["all", "individual"]:
            plotter = IndividualListingsPlotter(data_dir)
            plotter.generate_individual_listing_plots(model)
            logger.success("Individual listing plots generated")

        if plot_type in ["all", "year"]:
            year_plotter = YearAnalysisPlotter(data_dir)
            year_plotter.generate_year_analysis_plots(model)
            logger.success("Year analysis plots generated")

        logger.success(f"All {plot_type} plots generated successfully!")

    except Exception as e:
        logger.error(f"Plot generation failed: {e}")
        sys.exit(1)


@cli.command()
@click.option("--data-dir", default="./data", help="Directory containing data")
def status(data_dir: str):
    """
    📋 Show current data status and statistics

    Display information about scraped models, data sizes,
    and recent scraping activity.
    """
    logger.info(f"Checking status for data directory: {data_dir}")

    try:
        data_path = Path(data_dir)
        if not data_path.exists():
            logger.warning(f"Data directory does not exist: {data_dir}")
            return

        # Find all model directories
        model_dirs = [d for d in data_path.iterdir() if d.is_dir()]

        if not model_dirs:
            logger.info("No models found in data directory")
            return

        logger.info(f"Found {len(model_dirs)} models:")

        for model_dir in model_dirs:
            model_name = model_dir.name

            # Check for data files
            csv_files = list(model_dir.glob("*.csv"))
            json_files = list(model_dir.glob("*.json"))

            logger.info(f"  📁 {model_name}:")
            logger.info(f"    CSV files: {len(csv_files)}")
            logger.info(f"    JSON files: {len(json_files)}")

            # Get latest file modification time
            all_files = csv_files + json_files
            if all_files:
                latest_file = max(all_files, key=lambda f: f.stat().st_mtime)
                latest_time = datetime.fromtimestamp(latest_file.stat().st_mtime)
                logger.info(
                    f"    Last updated: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        sys.exit(1)


@cli.command(name="scrape-all")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="targets.db path (default: $TARGETS_DB or ./targets.db)",
)
@click.option("--data-dir", default="./data", help="Directory to save data")
@click.option("--max-pages", default=10, help="Maximum pages per target")
@click.option(
    "--alerts-file",
    default="data/alerts.md",
    help="Where to write the alert body (only if there is something to report)",
)
def scrape_all(db_path: str | None, data_dir: str, max_pages: int, alerts_file: str):
    """🚙 Scrape every target in targets.db and write an alert summary.

    This is what the daily pipeline runs. Each target has its own filtered
    otomoto URL so we only track the exact variants we care about.
    """
    from src.car_scraper.notifiers.pushover import send_pushover
    from src.car_scraper.reporting import format_alert_markdown, format_alert_pushover
    from src.car_scraper.storage.simplified_listings import SimplifiedListingsStorage
    from src.target_store import open_default_store

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
        # No sensible default: your dashboard is wherever you self-host it.
        dashboard_url = os.environ.get("DASHBOARD_URL")
        if send_pushover(title, message, url=dashboard_url, url_title="Open dashboard"):
            click.echo("🔔 Pushover notification sent")
    else:
        # No stale alert file lingering for the pipeline to act on.
        alerts_path.unlink(missing_ok=True)
        click.echo("\n✅ No new cars or price drops")


@cli.command()
@click.option("--data-dir", default="./data", help="Directory containing data")
@click.option("--output", default="plots/index.html", help="Output HTML file")
@click.option(
    "--db",
    "db_path",
    default=None,
    help="targets.db path (default: $TARGETS_DB or ./targets.db)",
)
def report(data_dir: str, output: str, db_path: str | None):
    """🖥️  Build the static HTML dashboard (interactive, no server needed)."""
    from src.car_scraper.reporting import build_static_report

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    path = build_static_report(data_dir, output, db_path, generated)
    logger.success(f"Static report written to {path}")
    click.echo(f"🖥️  Dashboard: {path}")


@cli.group()
def targets():
    """Manage tracked targets (stored in targets.db - see the dashboard's
    "Manage Targets" page for a form-based editor)."""


@targets.command("list")
@click.option("--db", "db_path", default=None, help="targets.db path")
def targets_list(db_path: str | None):
    """List configured targets."""
    from src.target_store import open_default_store

    rows = open_default_store(db_path).list_targets()
    if not rows:
        click.echo(
            "No targets configured yet - see the dashboard's Manage Targets page."
        )
        return
    for t in rows:
        tag = " [facets]" if t.get("facets") else ""
        click.echo(f"{t['key']:<20} {t['label']}{tag}")


@targets.command("import")
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, help="targets.db path")
@click.option(
    "--overwrite", is_flag=True, help="Replace existing targets that share a key"
)
def targets_import(json_file: str, db_path: str | None, overwrite: bool):
    """Import targets from a targets.json-shaped file (e.g. targets.example.json)."""
    from src.target_store import TargetStore

    n = TargetStore(db_path).import_json(json_file, overwrite=overwrite)
    click.echo(f"✅ Imported {n} target(s) from {json_file}")


@targets.command("remove")
@click.argument("key")
@click.option("--db", "db_path", default=None, help="targets.db path")
def targets_remove(key: str, db_path: str | None):
    """Remove one target by key."""
    from src.target_store import TargetStore

    if TargetStore(db_path).delete(key):
        click.echo(f"✅ Removed {key}")
    else:
        raise click.ClickException(f"No target with key {key!r}")


if __name__ == "__main__":
    cli()
