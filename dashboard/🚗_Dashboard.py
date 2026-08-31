"""Interactive car-tracker dashboard (Streamlit).

Standalone on purpose: reads data/<model>/<model>.json directly and only
imports src/target_store.py + src/facets.py (both stdlib-only) for the
target list/labels and the country/accident/damage classification, so the
container needs streamlit + plotly + pandas and nothing from the scraper
package's own (much heavier) dependencies. Run locally with `docker compose
up` (see docker-compose.yml) or `streamlit run dashboard/🚗_Dashboard.py`. See
also pages/ for the "Manage Targets" editor.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Repo root (parent of dashboard/) on sys.path so `from src.target_store
# import ...` resolves regardless of cwd - mirrors main.py's own sys.path
# setup. Must match dashboard/'s position relative to src/ in the Docker
# image too (see dashboard/Dockerfile) so this is identical in both places.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.facets import classify  # noqa: E402
from src.target_store import open_default_store  # noqa: E402

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = os.environ.get("TARGETS_DB")  # None -> target_store's own default


@st.cache_data(ttl=30)
def load_labels() -> dict:
    """Return {key: label} from targets.db (empty if missing/invalid)."""
    return {t["key"]: t["label"] for t in open_default_store(DB_PATH).list_targets()}


def _condition_label(accident_free, damaged) -> str:
    """One readable label from the (accident_free, damaged) pair."""
    if accident_free is True:
        return "✅ Bezwypadkowy"
    if accident_free is False:
        return "💥 Powypadkowy"
    if damaged is True:
        return "🔧 Uszkodzony"
    return "—"


def _relative_time(iso_str: str) -> str:
    """'3m ago' / '2h ago' / '5d ago' from an ISO timestamp, or '' if unparseable."""
    try:
        then = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return ""
    seconds = (datetime.now() - then).total_seconds()
    if seconds < 0:
        return ""
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


@st.cache_data(ttl=30)
def load_metadata(key: str) -> dict:
    """Just the ``metadata`` block (has ``last_updated``) - cheap, no facets work."""
    f = DATA_DIR / key / f"{key}.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("metadata", {}) if isinstance(data, dict) else {}


@st.cache_data(ttl=300)
def load_model(key: str) -> pd.DataFrame:
    """Load one model's listings into a DataFrame, tagged with facets.

    Adds ``origin`` (flag + country) and ``condition`` (accident/damage,
    text-derived - see src/facets.py for why this can't be exact) to every
    row, same classification the static HTML report uses.
    """
    f = DATA_DIR / key / f"{key}.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        st.error(f"Could not read data for {key}: {exc}")
        return pd.DataFrame()
    if isinstance(data, dict):
        listings = list(data.get("listings", {}).values())
    elif isinstance(data, list):
        listings = data
    else:
        listings = []
    for listing in listings:
        facets = classify(key, listing)
        listing["country"] = facets["country"]
        listing["origin"] = f"{facets['flag']} {facets['country']}".strip()
        listing["accident_free"] = facets["accident_free"]
        listing["damaged"] = facets["damaged"]
        listing["condition"] = _condition_label(
            facets["accident_free"], facets["damaged"]
        )
    return pd.DataFrame(listings)


def models_with_data() -> list:
    """List model keys that have a data file under DATA_DIR (tracked or not)."""
    if not DATA_DIR.exists():
        return []
    return sorted(
        d.name
        for d in DATA_DIR.iterdir()
        if d.is_dir() and (d / f"{d.name}.json").exists() and not d.name.startswith(".")
    )


st.set_page_config(page_title="Car Tracker", page_icon="🚗", layout="wide")
st.title("🚗 Car Tracker")

labels = load_labels()
with_data = models_with_data()
# Only currently-tracked targets, not every model that ever left data behind -
# removing a target in Manage Targets should hide it here too. Old data/
# stays on disk untouched (in case the target comes back) - see stale below.
available = [m for m in with_data if m in labels]
stale = [m for m in with_data if m not in labels]
if stale:
    st.sidebar.caption(
        f"{len(stale)} untracked model(s) still have data on disk: {', '.join(stale)}"
    )
if not available:
    if not labels:
        st.warning("No targets tracked yet - add one on the Manage Targets page.")
    else:
        st.warning(f"No data found in {DATA_DIR.resolve()} yet. Run the scraper first.")
    st.stop()

key = st.sidebar.selectbox("Model", available, format_func=lambda k: labels.get(k, k))
active_only = st.sidebar.checkbox("Active listings only", value=True)

df = load_model(key)
if "active" not in df.columns:
    df["active"] = True
if active_only:
    df = df[df["active"] != False]  # noqa: E712 - pandas truthiness

for col in ("year", "mileage", "current_price", "engine_power"):
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

if df.empty:
    st.info("No listings match the current filters.")
    st.stop()

# Optional year filter when the data spans multiple years.
if "year" in df.columns and df["year"].notna().any():
    ylo, yhi = int(df["year"].min()), int(df["year"].max())
    if yhi > ylo:
        lo, hi = st.sidebar.slider("Year", ylo, yhi, (ylo, yhi))
        df = df[df["year"].between(lo, hi)]

# No origin/condition filter widgets by design: filtering what you track
# belongs in the target's search URL (config), not a runtime UI layer on top
# of already-scraped data - see "Origin filtering" in README. origin/
# condition are still columns below, sortable by clicking the header.

if df.empty:
    st.info("No listings match the current filters.")
    st.stop()

last_updated = load_metadata(key).get("last_updated", "")
caption = labels.get(key, key)
if last_updated:
    when = _relative_time(last_updated)
    stamp = last_updated[:16].replace("T", " ")
    caption += f"  ·  Last scraped: {stamp}" + (f" ({when})" if when else "")
st.caption(caption)

c1, c2, c3, c4 = st.columns(4)
prices = df["current_price"].dropna()
c1.metric("Listings", len(df))
c2.metric("Avg price", f"{prices.mean():,.0f} zł" if len(prices) else "—")
c3.metric("Min price", f"{prices.min():,.0f} zł" if len(prices) else "—")
c4.metric("Max price", f"{prices.max():,.0f} zł" if len(prices) else "—")

# Price over time, one line per listing with history.
rows = []
for _, row in df.iterrows():
    for ts, price in row.get("price_readings") or []:
        if price and price > 0:
            rows.append(
                {
                    "id": f"#{row.get('internal_id')}",
                    "title": row.get("title"),
                    "date": datetime.fromtimestamp(ts),
                    "price": price,
                }
            )
left, right = st.columns(2)
if rows:
    hist = pd.DataFrame(rows)
    fig = px.line(
        hist,
        x="date",
        y="price",
        color="id",
        markers=True,
        hover_data=["title"],
        title="Price over time",
    )
    fig.update_layout(yaxis_title="PLN", xaxis_title="")
    left.plotly_chart(fig, width="stretch")

if "mileage" in df.columns and df["mileage"].notna().any():
    fig2 = px.scatter(
        df,
        x="mileage",
        y="current_price",
        color="year",
        hover_data=["title", "engine_power", "gearbox"],
        title="Price vs mileage",
        color_continuous_scale="Viridis",
    )
    fig2.update_layout(yaxis_title="PLN", xaxis_title="km")
    right.plotly_chart(fig2, width="stretch")

# Table, cheapest first, with clickable links and human-readable headers
# (a raw column_config-less dataframe just shows the JSON field names).
_COLUMN_LABELS = {
    "internal_id": "ID",
    "title": "Title",
    "year": "Year",
    "mileage": "Mileage (km)",
    "engine_power": "Power (KM)",
    "gearbox": "Gearbox",
    "version": "Version",
    "origin": "Origin",
    "condition": "Condition",
    "current_price": "Price (PLN)",
}
cols = [c for c in _COLUMN_LABELS if c in df.columns] + (
    ["url"] if "url" in df.columns else []
)
table = df[cols].sort_values("current_price", na_position="last")
column_config = {
    field: st.column_config.Column(label) for field, label in _COLUMN_LABELS.items()
}
column_config["url"] = st.column_config.LinkColumn("Link", display_text="open")
st.dataframe(table, width="stretch", hide_index=True, column_config=column_config)
