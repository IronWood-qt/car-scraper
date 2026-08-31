# 🚗 Car Scraper for Otomoto.pl

[![Tests](https://github.com/IronWood-qt/car-scraper/actions/workflows/test.yml/badge.svg)](https://github.com/IronWood-qt/car-scraper/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Scrapes car listings from otomoto.pl (+ autoplac.pl) with time-series price
tracking, shown in a self-hosted web dashboard. Listing data is read straight
from otomoto's embedded structured data (clean price / year / mileage /
engine power / gearbox / fuel type), so no fragile per-advert HTML scraping.

**Self-hosted by design**: both what you're searching for (`targets.db`) and
what it finds (`data/`) are gitignored and never committed, in this repo or a
fork, locally or in CI — this repo is code only. Run it wherever you control
the storage (a home server, a NAS, `./run.sh` or `docker compose up` - see
[🚀 Installation](#-installation)).

## 🚀 Installation

No Poetry needed to just *run* things - `run.sh` sets up a plain
`python3 -m venv` + `pip` on first use (finds a Python 3.10+ interpreter
itself) and you're done.

### `run.sh` (recommended for local/bare-metal use)

```bash
./run.sh          # dashboard -> http://localhost:8501 (the only thing you run by hand)
./run.sh scrape    # one-off manual scrape-all, for debugging
```

Everything else - which cars to track, max pages, Pushover, the scraper's
schedule - lives in the dashboard now: add a car from the main grid, paste
its otomoto/autoplac search URL on that car's own Settings tab, and tune
global knobs on ⚙️ App Settings. Nothing here is a flag anymore.

### Docker Compose (recommended for self-hosted/homelab)

The full stack (dashboard + a scheduled scraper container, no host cron) -
see [🖥️ Dashboards](#️-dashboards) below:

```bash
touch targets.db
docker compose up
```

### Poetry (for development)

Only needed for dev tooling (pytest/ruff/mypy/pre-commit) - see [💻 Local
Development](#-local-development) below. `poetry install --with dev` also
works fine as a third way to just run things, if you'd rather have Poetry
manage the venv than `run.sh`'s plain one.

## 🎯 Tracked targets

**Which cars you track is private, not project config: `targets.db` (SQLite)
is gitignored and never committed** (see [`.gitignore`](.gitignore)) — it
never touches git history, on any branch, in this repo or a fork. The
listings it finds (`data/`) are gitignored too, for the same reason — see
[🖥️ Dashboards](#️-dashboards).

Manage it entirely from the dashboard, no JSON editing required. The flow is
built around otomoto/autoplac's own search UI instead of reinventing filter
widgets:

1. Build your search on **otomoto.pl** (or autoplac.pl) directly - brand,
   model, year, price, whatever - using their filters.
2. Copy the resulting URL.
3. On the dashboard's main grid, **➕ Add target** with just a label. It
   opens straight to that new card's **⚙️ Settings** tab - paste the URL
   into **Sources** there and save.
4. From then on, that car's page has a **🔗 Go to otomoto** button in the
   sidebar - click it any time to re-open the *same* search live, tweak
   filters, and paste the refreshed URL back into Settings.

`targets.db` is created automatically the first time anything touches it. If
you have an old `targets.json` lying around from before targets.db existed,
that first run auto-imports it once - nothing to do by hand. Otherwise,
[`targets.example.json`](targets.example.json) is a real, working file you
can bulk-import as a starting point:
`.venv/bin/python -c "from src.target_store import TargetStore;
TargetStore().import_json('targets.example.json')"` (after `./run.sh` once
so `.venv` exists) - then edit each one from the dashboard.

Each target is, conceptually:

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
(that's the JSON *import* shape / roughly what a car's Settings tab fields
map to - it's stored relationally in `targets.db`, key is the primary key,
see [`src/target_store.py`](src/target_store.py).)

`sources` may be a single entry or several — listings from every source are
merged into one data file per `key`, deduplicated by listing id. `site` is
just documentation; the scraper is actually picked per-URL by domain, so any
otomoto.pl / autoplac.pl search URL works. Useful filter patterns: otomoto
takes a model-year floor as a path segment (`/od-2025`), autoplac as a query
param (`?yearFrom=2025`); both support `search[filter_enum_gearbox]=manual` /
`transmissionTypes=MANUAL` and similar facet filters — copy them straight
from the site's own search UI (see also "Origin filtering" under 🖥️
Dashboards). otomoto's model URL slug is sometimes hyphenated where the
display name isn't (e.g. Volvo XC90 → `xc-90`) — an unrecognized slug
doesn't error, it silently falls back to an unfiltered brand-wide search, so
**check the result count/listings actually match what you expect** before
trusting a new URL.

`facets` (optional) is what turns a variant/trim into filter chips on the
dashboard, entirely from config — no code needed for a new car. Each
dimension (`variant` / `trim` / `body`, all optional) is an ordered list of
`{label, keywords}` rules checked top to bottom; the first whose keywords
appear (whole-word, case-insensitive) in the listing's title/description
wins, so put more specific labels first. `targets.example.json` has a real,
working second example (Lexus LC's actual V8/hybrid + trim split, purely as
config) you can import as-is. A handful of the originally-tracked models
(Lexus LC, Mazda MX-5, Toyota Supra/GR86) also have their facet logic
hardcoded in [`facets.py`](src/facets.py) from before this config
existed — new targets don't need that, a `facets` block covers it; when a
target has one, it always wins over any hardcoded classifier for that key.

### Optional: the `TARGETS_JSON` CI secret

The included GitHub Actions workflow ([`daily-scrape.yml`](.github/workflows/daily-scrape.yml))
is disabled by default (manual trigger only) — the recommended path is
running this yourself, self-hosted (see [🖥️ Dashboards](#️-dashboards)),
since GitHub Actions has nowhere private to persist `data/` (or `targets.db`)
between runs (see that workflow's file header for why). If you ever do want
to manually trigger it, it checks out the repo fresh and so has neither;
give it a copy of your targets via a repo secret instead: *Settings → Secrets
and variables → Actions → New repository secret* → name `TARGETS_JSON`,
value = `targets.example.json`-shaped JSON (export yours with
`.venv/bin/python -c "from src.target_store import TargetStore;
TargetStore().export_json('out.json')"` after `./run.sh` once so `.venv`
exists). The workflow writes it to `targets.json`, which the first run of
`main.py` auto-imports into a fresh `targets.db` right there in the runner -
fails fast (with a clear error) if the secret is unset or the JSON is
invalid, and it's never logged (secrets are masked) or written anywhere but
the ephemeral runner's disk.

## 🖥️ Dashboards

**Self-hosted (recommended)**:

```bash
touch targets.db          # first time only - see the docker-compose.yml comment for why
cp .env.example .env      # optional: Pushover creds - see .env.example
docker compose up         # -> http://localhost:8501
```

Two containers: `dashboard` (the web UI, below) and `scraper` (runs a
scrape on a loop, keeping `data/` fresh - see [🤖 Scheduling](#-scheduling)).
Nothing to run on the host, nothing to leave running in a terminal.

The dashboard is a single-page Streamlit app (plus one sidebar-nav page for
global settings) built around otomoto's own search UI rather than
reinventing filter widgets:

- **🚗 Dashboard (home)** — a card grid, one per tracked target: a real photo
  (the cheapest active listing's own thumbnail - swapped in as soon as
  there's at least one scraped listing with one, otherwise the 🚗 icon),
  last-scraped date/time, listings count, and avg price with the %-change
  vs. the previous scrape (green = cheaper, red = pricier, grey when it
  hasn't moved). **➕ Add target** at the bottom just takes a label - no URL
  required up front.
- **A target's page** (click its card) — two tabs:
  - **📊 Overview** — the "🔄 Update now" button, year filter,
    price-over-time / price-vs-mileage charts, and a sortable linked table
    reading `data/` straight off disk. Every listing also gets an
    **origin** (country) and a **condition**
    (bezwypadkowy/powypadkowy/uszkodzony) column - both text-derived (see
    [`src/facets.py`](src/facets.py)), no filter widgets for either by
    design: narrowing what you *track* belongs in the target's search URL,
    not a runtime filter layered on top of already-scraped data (see
    "Origin filtering" below) - click a column header to sort instead.
    otomoto's search results carry no structured accident/damage field
    (only the individual advert page does, which this project deliberately
    doesn't scrape), so condition is a text match against the
    title/description and **a miss means "not mentioned," not "confirmed
    undamaged."**
  - **⚙️ Settings** — label, note, source URLs (see [🎯 Tracked
    targets](#-tracked-targets) above), optional facet-chip rules, and
    delete.
  - The sidebar also has a **🔗 Go to otomoto** (/autoplac) button per
    source - opens that exact search live on the site, for rebuilding
    filters or just manually browsing the listings yourself.
- **⚙️ App Settings** — max pages per target, the scraper container's loop
  interval, Pushover credentials, the dashboard URL alerts link to - see
  below. Global, not per-car.

Point the compose volumes at a home server / NAS and it's a permanent,
private web dashboard on your own network — nothing about what you track or
find ever leaves that box.

### Origin filtering

Both otomoto and autoplac support filtering by country of origin natively in
the search URL - narrow what you *scrape* instead of filtering what's
already scraped. otomoto: append
`search[filter_enum_country_origin][0]=<code>` (`usa`, `d` for Germany, `f`
for France, `pl` for Poland, ... - the same codes `src/facets.py`'s
`_FLAGS` maps to flags); autoplac exposes an equivalent country picker in
its own UI - copy the resulting URL. Add it straight to the target's source
URL on that car's Settings tab, e.g. for USA-only:
`https://www.otomoto.pl/osobowe/volvo/xc-90/od-2025?search%5Bfilter_enum_country_origin%5D%5B0%5D=usa`
(verified live: narrows 237 XC90 results down to exactly the USA-imported
ones).

## ⚙️ App Settings

The dashboard's global App Settings page (not per-car - see [🖥️
Dashboards](#️-dashboards) above), backed by `targets.db` (see
[`src/settings_store.py`](src/settings_store.py)):

| Setting | Default | Notes |
|---|---|---|
| Max pages per target | 10 | Passed to every target's search during a scrape |
| Scraper loop interval | 6h | `docker-compose.yml`'s `scraper` container re-reads this **every cycle** - change it and the next sleep picks it up, no restart needed |
| Pushover application token / user key | unset | See [🔔 Alerts](#-alerts) |
| Dashboard URL | unset | Linked from Pushover alerts |

Every field also has an env var fallback (`PUSHOVER_TOKEN`, `PUSHOVER_USER`,
`DASHBOARD_URL` - see [`.env.example`](.env.example)) used only when the
Settings-page value is empty - handy if you'd rather not put secrets in
`targets.db`, or want them set before you've opened the dashboard once.

## 🔔 Alerts

Every scrape that finds a new listing or a price drop can fire two channels:

- **Pushover push notification** — a compact summary (title + up to 5 items
  per section) sent to your phone/desktop via [Pushover](https://pushover.net).
  Configure via the App Settings page (or `PUSHOVER_TOKEN`/`PUSHOVER_USER`, see
  above); unset on both means this silently no-ops. This is the channel that
  actually fits self-hosted use.
- **GitHub issue** — opens (or comments on) an issue titled **"🚗 Car
  alerts"**, only when a scrape runs inside the (disabled-by-default,
  manual-only) GitHub Actions workflow — see [🎯 Tracked
  targets](#-tracked-targets) above. Not applicable when you run this
  yourself locally/self-hosted.

## 🤖 Scheduling

There's no automated daily scraping in GitHub Actions anymore (see 🎯 Tracked
targets / 🖥️ Dashboards above for why) — `data/` has nowhere private to live
there between runs, so a GitHub-hosted schedule would just re-report every
listing as "new" on every run.

`docker compose up` runs the scheduling itself now: alongside `dashboard`, a
`scraper` container loops a scrape on an interval (default 6h, editable on
the App Settings page - see above), sharing the same `./data` and `./targets.db`
the dashboard reads/edits. No host cron needed; `docker compose logs -f
scraper` to watch it, `docker compose restart scraper` to force an
immediate run. It's a plain `while true; sleep` loop (see the `command:` in
`docker-compose.yml`), not a real cron daemon - fine for one periodic job,
but note a restart of the container resets the wait (no persisted "last ran
at").

Prefer bare metal, or want a schedule cron actually understands? Skip the
`scraper` service and use a host cron job / systemd timer calling
`./run.sh scrape` from the repo checkout instead - it writes into the same
`./data` the dashboard container mounts either way.

[`daily-scrape.yml`](.github/workflows/daily-scrape.yml) still exists,
manual-dispatch-only, if you ever want to run it once in GitHub Actions
anyway — see [Optional: the `TARGETS_JSON` CI
secret](#optional-the-targets_json-ci-secret) above for what it needs.

## 🏗️ Project Structure

```
car-scraper/
├── src/
│   ├── target_store.py         # SQLite CRUD for targets.db (stdlib-only, shared by CLI + dashboard)
│   ├── settings_store.py       # SQLite CRUD for Settings (stdlib-only, shared)
│   ├── facets.py                # Origin/condition/variant/trim classification (stdlib-only, shared)
│   └── car_scraper/             # Main package
│       ├── scrapers/               # otomoto.pl / autoplac.pl search-page scraping
│       ├── storage/                # data/*.json persistence + price-history tracking
│       └── utils/                  # Logging, DataProcessor
├── dashboard/                   # Streamlit web UI (standalone container - see dashboard/Dockerfile)
│   ├── 🚗_Dashboard.py              # Card grid (home) + per-car Overview/Settings tabs
│   └── pages/
│       └── 1_⚙️_App_Settings.py       # Max pages, scrape interval, Pushover, dashboard URL
├── data/                        # Model-specific data storage (gitignored, not committed)
│   └── {model}/{model}.json        # Unified data file: listings + full price history
├── targets.db                   # SQLite: tracked targets + settings (gitignored, not committed)
├── tests/                       # Test suite
├── .github/workflows/           # GitHub Actions (tests; a disabled/manual scrape workflow)
├── Dockerfile                    # CLI image (ENTRYPOINT: main.py) - the scraper service uses this
├── docker-compose.yml            # Full stack: dashboard + scheduled scraper
├── .env.example                   # Pushover creds / dashboard URL fallback - copy to .env
├── run.sh                        # No-Poetry entry point (dashboard by default)
└── main.py                      # scrape-all engine (invoked by run.sh/docker-compose, not by hand)
```

## 💻 Local Development

```bash
# Install dev dependencies (pytest/ruff/mypy/pre-commit) + everything to run things too
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

## 📁 Data Structure

Each model gets one file, `data/{model}/{model}.json`:

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
        {"price": 450000, "date": "2025-05-31", "timestamp": 1732890123}
      ]
    }
  }
}
```

Price history is integrated - every reading for a listing lives in its own
`price_readings`, so the file is a complete, append-only record even as
listings go inactive (kept, not deleted, when they drop off a search).

## 🛠️ Technical Details

### Technologies

- **Python 3.10+**, **Poetry** for dependency management (dev tooling only - see 🚀 Installation)
- **Click** - the one remaining CLI command (`main.py`'s scrape engine)
- **Streamlit + Plotly + Pandas** - the dashboard (standalone, see `dashboard/requirements.txt`)
- **Pydantic**, **HTTPX**, **BeautifulSoup4/lxml**, **Loguru** - scraping + validation
- **SQLite** (stdlib `sqlite3`, WAL mode) - `targets.db` (targets + settings), shared safely between the dashboard and scraper containers

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
