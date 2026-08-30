# 🚗 Car Scraper for Otomoto.pl

[![Tests](https://github.com/IronWood-qt/car-scraper/actions/workflows/test.yml/badge.svg)](https://github.com/IronWood-qt/car-scraper/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency--management-poetry-blue)](https://python-poetry.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A CLI that scrapes car listings from otomoto.pl with time-series price tracking,
analysis, and visualization. Listing data is read straight from otomoto's
embedded structured data (clean price / year / mileage / engine power / gearbox
/ fuel type), so no fragile per-advert HTML scraping.

**Self-hosted by design**: both what you're searching for (`targets.json`)
and what it finds (`data/`) are gitignored and never committed, in this repo
or a fork, locally or in CI — this repo is code only. Run it wherever you
control the storage (a home server, a NAS, `docker compose up`); see
[🖥️ Dashboards](#️-dashboards) below.

## 🎯 Tracked targets

**Which cars you track is private, not project config: `targets.json` is
gitignored and never committed** (see [`.gitignore`](.gitignore)) — it never
touches git history, on any branch, in this repo or a fork. The listings it
finds (`data/`) are gitignored too, for the same reason — see [🖥️
Dashboards](#️-dashboards). Set yours up once:

```bash
cp targets.example.json targets.json
# then edit targets.json - it's yours, git will never see it
```

Each target in `targets.json`:

```json
{
  "key": "make-model",
  "label": "Human-readable name shown in the dashboard/alerts",
  "sources": [
    {"site": "otomoto", "url": "https://www.otomoto.pl/osobowe/<make>/<model>?<filters>"},
    {"site": "autoplac", "url": "https://autoplac.pl/oferty/samochody-osobowe/<make>/<model>?<filters>"}
  ],
  "note": "optional: what the filters mean, for your own future reference",
  "facets": {
    "variant": [
      {"label": "T8", "keywords": ["t8", "recharge"]},
      {"label": "B5", "keywords": ["b5"]}
    ],
    "trim": [
      {"label": "Ultimate", "keywords": ["ultimate"]},
      {"label": "Plus", "keywords": ["plus"]}
    ]
  }
}
```

`sources` may be a single entry or several — listings from every source are
merged into one data file per `key`, deduplicated by listing id. `site` is
just documentation; the scraper is actually picked per-URL by domain, so any
otomoto.pl / autoplac.pl search URL works. A bare `{"url": "..."}` (no
`sources` array) also still works for a single-source target. Useful filter
patterns: otomoto takes a model-year floor as a path segment
(`/od-2025`), autoplac as a query param (`?yearFrom=2025`); both support
`search[filter_enum_gearbox]=manual` / `transmissionTypes=MANUAL` and
similar facet filters — copy them straight from the site's own search UI.
otomoto's model URL slug is sometimes hyphenated where the display name
isn't (e.g. Volvo XC90 → `xc-90`) — an unrecognized slug doesn't error, it
silently falls back to an unfiltered brand-wide search, so **check the result
count/listings actually match what you expect** before trusting a new URL.

`facets` (optional) is what turns a variant/trim into filter chips on the
dashboard, entirely from config — no code needed for a new car. Each
dimension (`variant` / `trim` / `body`, all optional) is an ordered list of
`{label, keywords}` rules checked top to bottom; the first whose keywords
appear (whole-word, case-insensitive) in the listing's title/description
wins, so put more specific labels first. `targets.example.json` has a real,
working second example (Lexus LC's actual V8/hybrid + trim split, purely as
config) you can scrape as-is. A handful of the originally-tracked models
(Lexus LC, Mazda MX-5, Toyota Supra/GR86) also have their facet logic
hardcoded in [`facets.py`](src/car_scraper/facets.py) from before this config
existed — new targets don't need that, `facets` in `targets.json` covers it;
if a target's own JSON has a `facets` block it always wins over any hardcoded
classifier for that key.

### Optional: the `TARGETS_JSON` CI secret

The included GitHub Actions workflow ([`daily-scrape.yml`](.github/workflows/daily-scrape.yml))
is disabled by default (manual trigger only) — the recommended path is
running this yourself, self-hosted (see [🖥️ Dashboards](#️-dashboards)),
since GitHub Actions has nowhere private to persist `data/` between runs (see
that workflow's file header for why). If you ever do want to manually
trigger it, it checks out the repo fresh and so never has your local
`targets.json`; give it one via a repo secret instead: *Settings → Secrets
and variables → Actions → New repository secret* → name `TARGETS_JSON`,
value = the full contents of your local `targets.json`. The workflow writes
it to `targets.json` at the start of the run and fails fast (with a clear
error) if the secret is unset or the JSON is invalid - it's never logged
(secrets are masked) or written anywhere but the ephemeral runner's disk.

## 🖥️ Dashboards

**Self-hosted (recommended)** — `docker compose up` → http://localhost:8501,
a Streamlit app with model/year filters, price-over-time charts and a
sortable, linked table, reading `data/` straight off disk. Point it at a
volume on a home server / NAS and it's a permanent, private web dashboard on
your own network — nothing about what you track or find ever leaves that
box. Pair it with a scheduler (cron, systemd timer, etc.) running
`car-scraper scrape-all` periodically to keep `data/` fresh.

There's also `car-scraper report`, which writes a self-contained, interactive
`plots/index.html` (Plotly, no server) plus per-model PNGs under
`plots/{model}/` — handy for a quick static snapshot, or to publish somewhere
yourself if you ever do want a public view. Both `data/` and `plots/` are
gitignored (see [🎯 Tracked targets](#-tracked-targets) above) - generated
locally, never committed, so none of it grows the repo either.

## 🔔 Alerts

Every `car-scraper scrape-all` run that finds a new listing or a price drop
can fire two channels:

- **Pushover push notification** — a compact summary (title + up to 5 items
  per section) sent to your phone/desktop via [Pushover](https://pushover.net).
  Opt-in: `export PUSHOVER_TOKEN=... PUSHOVER_USER=...` (application token +
  user/group key) before running `scrape-all`; without them this silently
  no-ops. This is the channel that actually fits self-hosted use.
- **GitHub issue** — opens (or comments on) an issue titled **"🚗 Car
  alerts"**, only when `scrape-all` runs inside the (disabled-by-default,
  manual-only) GitHub Actions workflow — see [🎯 Tracked
  targets](#-tracked-targets) above. Not applicable when you run this
  yourself locally/self-hosted.

## ✨ Features

- **Model-Specific Organization**: Separate data directories and plots for each car model
- **Advanced Scraping**: Extract car listings with prices, specifications, and metadata
- **Time Series Tracking**: Monitor individual listings over time for price analysis
- **Rich Visualizations**: Generate comprehensive plots and analysis charts organized by model
- **Multiple Data Formats**: Support for both CSV and JSON data formats
- **Professional CLI**: Modern Click-based command-line interface
- **Modular Architecture**: Clean, maintainable codebase following PEP standards
- **Type Safety**: Full type hints with Pydantic data validation
- **Quality Tooling**: Ruff (lint + format), mypy, bandit, and pytest
- **Docker Support**: Self-hosted deployment via `docker compose up` (see 🖥️ Dashboards)
- **Push Alerts**: Pushover notifications on new listings / price drops

## 🚀 Installation

### Poetry (Recommended)

1. **Install dependencies**:
```bash
poetry install
```

2. **Activate virtual environment**:
```bash
poetry shell
```

3. **Use the CLI**:
```bash
car-scraper --help
```

### Pip Installation

1. **Install in development mode**:
```bash
pip install -e .
```

2. **Use the CLI**:
```bash
car-scraper --help
```

### Docker

1. **Build the Docker image**:
```bash
docker build -t car-scraper .
```

2. **Run with Docker**:
```bash
docker run -v $(pwd)/data:/app/data car-scraper --help
```

## 📖 Usage

### Quick Start

```bash
# Scrape every target in targets.json - run this on your own schedule
car-scraper scrape-all --max-pages 5

# Build the interactive static dashboard (plots/index.html)
car-scraper report

# Local Docker dashboard at http://localhost:8501
docker compose up
```

### Single-model commands

```bash
# Simple mode - specify manufacturer and model
car-scraper scrape --manufacturer lexus --model lc --max-pages 2

# Advanced mode - use URL for specific queries
car-scraper scrape --url "https://www.otomoto.pl/osobowe/lexus/lc?custom=filters" --max-pages 2

# Generate all plots
car-scraper plot --model "lexus-lc" --plot-type "all"

# Check data status
car-scraper status
```

### Available Commands

#### 🔍 Scraping

The scraper supports two modes for flexibility:

**Simple Mode** - Auto-generates URL from manufacturer and model:
```bash
# Basic scraping
car-scraper scrape --manufacturer lexus --model lc

# With options
car-scraper scrape \
    --manufacturer bmw \
    --model i8 \
    --max-pages 5 \
    --delay 2.0 \
    --format json
```

**Advanced Mode** - Use custom URLs for specific queries:
```bash
# Custom URL (auto-detects manufacturer/model)
car-scraper scrape --url "https://www.otomoto.pl/osobowe/lexus/lc?specific=filters"

# URL with overrides
car-scraper scrape \
    --url "https://www.otomoto.pl/osobowe/lexus/lc" \
    --manufacturer lexus \
    --model lc-special \
    --max-pages 3
```

#### 📊 Plotting

```bash
# Generate all plots
car-scraper plot --model "lexus-lc" --plot-type "all"

# Generate specific plot types
car-scraper plot --model "lexus-lc" --plot-type "individual"  # Price trends
car-scraper plot --model "lexus-lc" --plot-type "year"       # Year analysis
```

#### 📋 Status

```bash
# Check data status
car-scraper status
```

## 🏗️ Project Structure

```
car-scraper/
├── src/car_scraper/           # Main package
│   ├── models/                # Pydantic data models
│   ├── scrapers/              # Web scraping modules
│   ├── storage/               # Data persistence
│   ├── plotters/              # Visualization modules
│   └── utils/                 # Utilities and helpers
├── data/                      # Model-specific data storage (gitignored, not committed)
│   ├── {model}/               # Per-model directories
│   │   └── {model}.json       # Unified data file with listings and price history
│   └── ...                    # Additional models
├── plots/                     # Generated dashboard (gitignored, not committed)
│   ├── index.html             # Interactive Plotly dashboard (static, optional)
│   ├── {model}/               # Per-model plot directories
│   │   ├── year_analysis.png  # Year-based analysis
│   │   ├── price_vs_mileage.png # Value correlation
│   │   └── listings_by_year.png # Distribution plots
│   └── ...                    # Additional models
├── tests/                     # Test suite
├── .github/workflows/         # GitHub Actions
└── main.py                    # CLI entry point
```

## 🤖 Scheduling

There's no automated daily scraping in this repo anymore (see 🎯 Tracked
targets / 🖥️ Dashboards above for why) — `data/` has nowhere private to live
in GitHub Actions between runs, so a GitHub-hosted schedule would just
re-report every listing as "new" on every run. Run `car-scraper scrape-all`
on your own schedule instead, wherever `data/` actually persists:

- `docker-compose.yml` only runs the dashboard container (reads `./data`
  read-only) — scraping itself isn't containerized, so schedule it on the
  host: a cron job or systemd timer calling `poetry run python main.py
  scrape-all --max-pages 5` from the repo checkout, writing into the same
  `./data` the dashboard container mounts.

[`daily-scrape.yml`](.github/workflows/daily-scrape.yml) still exists,
manual-dispatch-only, if you ever want to run it once in GitHub Actions
anyway (e.g. to sanity-check the Pages deploy step) — see [Optional:
the `TARGETS_JSON` CI secret](#optional-the-targets_json-ci-secret) above for
what it needs.

## 💻 Local Development

### Setting Up Development Environment

```bash
# Install development dependencies
poetry install --with dev

# Install pre-commit hooks
poetry run pre-commit install

# Run tests
poetry run pytest

# Run type checking
poetry run mypy src/

# Lint + format (ruff replaces black/isort/flake8)
poetry run ruff check --fix .
poetry run ruff format .
```

## 📊 CLI Command Reference

### 🔍 `scrape` - Extract Car Listings

```bash
car-scraper scrape [OPTIONS]
```

**Options:**
- `--url TEXT` - Search URL from otomoto.pl (required)
- `--model TEXT` - Model name to save data as (required)
- `--data-dir TEXT` - Directory to save data (default: ./data)
- `--max-pages INTEGER` - Maximum number of pages to scrape (default: 10)
- `--format [csv|json]` - Output format (default: csv)
- `--delay FLOAT` - Delay between requests in seconds (default: 1.0)

**Examples:**
```bash
# Basic scraping
car-scraper scrape --url "https://www.otomoto.pl/osobowe/lexus/lc" --model "lexus-lc"

# Advanced options
car-scraper scrape \
  --url "https://www.otomoto.pl/osobowe/lexus/lc" \
  --model "lexus-lc" \
  --max-pages 3 \
  --delay 2.0 \
  --format json
```

### 📊 `plot` - Generate Visualizations

```bash
car-scraper plot [OPTIONS]
```

**Options:**
- `--model TEXT` - Model name to generate plots for (required)
- `--data-dir TEXT` - Directory containing data (default: ./data)
- `--plot-type [all|individual|year]` - Type of plots to generate (default: all)
- `--output-dir TEXT` - Directory to save plots (default: ./plots)

**Plot Types:**
- `individual` - Individual listing price trends over time
- `year` - Year-based analysis (price vs year, mileage analysis)
- `all` - Generate all plot types

**Examples:**
```bash
# Generate all plots
car-scraper plot --model "lexus-lc"

# Generate specific plot type
car-scraper plot --model "lexus-lc" --plot-type "year"
```

### 📋 `status` - Data Status Report

```bash
car-scraper status [OPTIONS]
```

**Options:**
- `--data-dir TEXT` - Directory containing data (default: ./data)

**Output:**
- Models found and record counts
- File sizes and last update times
- Data directory structure overview

## 📁 Data Structure

### Raw Data Files
```
data/
├── {model}/                  # Model-specific directories
│   └── {model}.json         # Unified data file with listings, price history, and metadata
└── ...                      # Additional models

plots/
├── {model}/                 # Model-specific plot directories
│   ├── year_analysis.png    # Comprehensive year analysis
│   ├── price_vs_mileage.png # Price-mileage correlation
│   ├── listings_by_year.png # Distribution by year
│   └── ...                  # Additional plot types
└── ...                      # Additional models
```

### Data Fields

Each scraped listing contains:
- `id` - Unique listing identifier from otomoto.pl
- `title` - Car title/description
- `price` - Price in PLN (Polish Złoty)
- `year` - Manufacturing year
- `mileage` - Mileage in kilometers (optional)
- `url` - Direct link to the listing
- `model` - Model name (as specified during scraping)
- `scrape_date` - Date of scraping (YYYY-MM-DD)
- `scrape_timestamp` - Unix timestamp of scraping

### Simplified Storage Format

The new simplified storage system uses a single JSON file per model with the following structure:

```json
{
  "metadata": {
    "model": "lexus-lc",
    "last_updated": "2025-05-31",
    "total_listings": 45,
    "total_price_readings": 123
  },
  "listings": {
    "listing_id_1": {
      "id": "listing_id_1",
      "title": "Lexus LC 500 2021",
      "current_price": 450000,
      "year": 2021,
      "mileage": 15000,
      "url": "https://...",
      "model": "lexus-lc",
      "first_seen": "2025-05-31",
      "last_seen": "2025-05-31",
      "price_readings": [
        {
          "price": 450000,
          "date": "2025-05-31",
          "timestamp": 1732890123
        }
      ]
    }
  }
}
```

This format provides:
- **Integrated price tracking** - All price history within each listing
- **Simplified file structure** - Single JSON file per model
- **Metadata tracking** - Summary statistics and model information
- **Historical preservation** - Maintains listings even when they're no longer active

## 🛠️ Technical Details

### Architecture

- **Modular Design**: Separated concerns (scraping, storage, plotting, utilities)
- **Type Safety**: Full type hints with Pydantic validation
- **Error Handling**: Comprehensive error handling and logging
- **Async Support**: Built for future async/concurrent scraping
- **Extensible**: Easy to add new car models and data sources

### Technologies

- **Python 3.10+** - Modern Python with type hints
- **Poetry** - Dependency management and packaging
- **Click** - Command-line interface framework
- **Pydantic** - Data validation and settings management
- **BeautifulSoup4** - HTML parsing and web scraping
- **Pandas** - Data manipulation and analysis
- **Matplotlib** - Data visualization and plotting
- **Loguru** - Structured logging
- **HTTPX** - HTTP client for web requests

### Quality Assurance

- **Ruff** - Linting + formatting (replaces black, isort, flake8)
- **MyPy** - Static type checking (pydantic plugin)
- **Bandit** - Security scanning
- **Pytest** - Test framework
- **pre-commit** - Runs all of the above on every commit

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Install dependencies**: `poetry install --with dev`
4. **Make your changes** with proper type hints and tests
5. **Run quality checks**:
   ```bash
   poetry run ruff check --fix .
   poetry run ruff format .
   poetry run mypy src/
   poetry run pytest
   ```
6. **Commit your changes**: `git commit -m 'Add amazing feature'`
7. **Push to the branch**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

## ⚠️ Disclaimer

This tool is for educational and research purposes. Please respect otomoto.pl's robots.txt and terms of service. Use reasonable delays between requests and avoid overwhelming their servers.

## 🐛 Issues & Support

If you encounter any issues or have suggestions for improvements:

1. Check the [Issues](../../issues) page for existing reports
2. Create a new issue with detailed information:
   - Python version
   - Operating system
   - Error messages or unexpected behavior
   - Steps to reproduce

## 🚀 Future Enhancements

- [ ] Additional car websites support
- [ ] Real-time price alerts
- [ ] Advanced filtering options
- [ ] Web dashboard interface
- [ ] Machine learning price predictions
- [ ] Database storage backend
- [ ] API endpoints for data access
