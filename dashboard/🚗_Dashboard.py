"""Interactive car-tracker dashboard (Streamlit).

One page, two views, switched via ``st.query_params["car"]`` (no separate
"Manage Targets" page anymore):

- No ``car`` param: a grid of cards, one per tracked target (listings count,
  avg price with %-change vs the previous scrape), plus "Add target".
- ``car=<key>``: that target's page, with an Overview tab (charts/table,
  same as before) and a Settings tab (label/note/sources/delete).
  The otomoto/autoplac search URL is pasted in on the Settings tab - build
  it by using the site's own filter UI, then "Go to <site>" in the sidebar
  jumps straight back there to tweak filters and copy a fresh URL.

Standalone on purpose: reads data/<model>/<model>.json directly and only
imports src/target_store.py + src/settings_store.py + src/facets.py (all
stdlib-only) so the container needs streamlit + plotly + pandas and nothing
from the scraper package's own (much heavier) dependencies. Run locally with
`docker compose up` (see docker-compose.yml) or
`streamlit run "dashboard/🚗_Dashboard.py"`.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Repo root (parent of dashboard/) on sys.path so `from src.target_store
# import ...` resolves regardless of cwd. Must match dashboard/'s position
# relative to src/ in the Docker image too (see dashboard/Dockerfile).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from _nav import render_nav  # noqa: E402

from src.facets import classify  # noqa: E402
from src.settings_store import SettingsStore  # noqa: E402
from src.target_store import TargetStoreError, open_default_store  # noqa: E402

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = os.environ.get("TARGETS_DB")  # None -> target_store's own default
# Only present bare-metal (dashboard/Dockerfile never copies main.py or the
# scraper package's own dependencies into the dashboard image - see there).
_MAIN_PY = REPO_ROOT / "main.py"
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

st.set_page_config(page_title="Car Tracker", page_icon="🚗", layout="wide")
store = open_default_store(DB_PATH)


# --------------------------------------------------------------------------
# Data loading (shared by the grid's price stats and the Overview tab)
# --------------------------------------------------------------------------


def _trigger_update_now() -> None:
    """Scrape every tracked target right now (all of them - scrape-all has
    no per-model mode). Always records the request in Settings so the
    docker-compose 'scraper' container (a separate, dependency-having
    container - see docker-compose.yml) can pick it up within ~15s instead
    of waiting out its full interval; when main.py is right here on disk
    (bare-metal `./run.sh`), also just runs it directly, synchronously.
    """
    SettingsStore(DB_PATH).set("trigger_scrape_at", int(time.time()))
    if not _MAIN_PY.exists():
        st.info("Requested - the scraper container will pick this up shortly.")
        return
    with st.spinner("Scraping every target..."):
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "."],
            cwd=REPO_ROOT,
            check=False,
        )
        result = subprocess.run(
            [sys.executable, str(_MAIN_PY)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode == 0:
        st.success("Done.")
    else:
        st.error(f"Scrape failed:\n{(result.stderr or result.stdout)[-800:]}")


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
    row. Assumes the data file exists - callers check ``models_with_data()``
    first so a not-yet-scraped target doesn't surface a scary read error.
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


def _active_only(df: pd.DataFrame) -> pd.DataFrame:
    if "active" not in df.columns:
        return df
    return df[df["active"] != False]  # noqa: E712 - pandas truthiness


def _price_stats(key: str) -> dict:
    """Active-listing count, avg price, and %-change vs the previous scrape
    run (each store_listings_data() call stamps every reading it adds with
    the same timestamp, so grouping readings by exact timestamp gives one
    number per run - see src/car_scraper/storage/simplified_listings.py)."""
    if key not in models_with_data():
        return {"count": 0, "avg": None, "pct": None}
    df = _active_only(load_model(key))
    if df.empty or "current_price" not in df.columns:
        return {"count": len(df), "avg": None, "pct": None}
    prices = pd.to_numeric(df["current_price"], errors="coerce").dropna()
    avg = prices.mean() if len(prices) else None
    pct = None
    readings = []
    if "price_readings" in df.columns:
        for row in df["price_readings"]:
            for ts, price in row or []:
                if price and price > 0:
                    readings.append((ts, price))
    if readings:
        by_ts = (
            pd.DataFrame(readings, columns=["ts", "price"])
            .groupby("ts")["price"]
            .mean()
            .sort_index()
        )
        if len(by_ts) >= 2:
            prev, latest = by_ts.iloc[-2], by_ts.iloc[-1]
            if prev:
                pct = (latest - prev) / prev * 100
    return {"count": len(df), "avg": avg, "pct": pct}


def _target_image(key: str) -> str | None:
    """One representative photo for a target - the cheapest active listing's
    otomoto/autoplac thumbnail (real photos scraped from real listings, not
    a fetched stock photo - no listing has one only for very recent otomoto
    listings that haven't finished indexing yet)."""
    if key not in models_with_data():
        return None
    df = _active_only(load_model(key))
    if df.empty or "image_url" not in df.columns:
        return None
    df = df[df["image_url"].notna()]
    if df.empty:
        return None
    if "current_price" in df.columns:
        df = df.sort_values("current_price", na_position="last")
    return df.iloc[0]["image_url"]


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return slug or "target"


def _unique_key(base: str) -> str:
    existing = {t["key"] for t in store.list_targets()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


# --------------------------------------------------------------------------
# Grid view (home)
# --------------------------------------------------------------------------


def _render_card(t: dict) -> None:
    key = t["key"]
    with st.container(border=True):
        img_url = _target_image(key)
        if img_url:
            st.image(img_url, width="stretch")
        st.markdown(f"#### {t['label']}")
        last_updated = (
            load_metadata(key).get("last_updated", "")
            if key in models_with_data()
            else ""
        )
        if last_updated:
            stamp = last_updated[:16].replace("T", " ")
            st.caption(f"🕓 Last scraped: {stamp}")
        stats = _price_stats(key)
        c1, c2 = st.columns(2)
        c1.metric("Listings", stats["count"])
        if stats["avg"] is not None:
            pct = stats["pct"]
            if pct is None:
                delta, color = None, "off"
            elif abs(pct) < 0.05:
                # A real reading but no real move - still show the arrow the
                # user expects on every card (needs an explicit '+' for
                # st.metric to draw one at all), just neutral color instead
                # of a misleading red/green for float noise around zero.
                delta, color = f"{pct:+.1f}%", "off"
            else:
                # A price *drop* is the good news here (see price_drops
                # alerts) - inverse so down=green, up=red.
                delta, color = f"{pct:+.1f}%", "inverse"
            c2.metric(
                "Avg price", f"{stats['avg']:,.0f} zł", delta=delta, delta_color=color
            )
        else:
            c2.metric("Avg price", "—")
        if not t.get("sources"):
            st.caption("⚠️ No otomoto URL yet - open, then add one in Settings.")
        if st.button("Open →", key=f"open_{key}", width="stretch"):
            st.query_params["car"] = key
            st.query_params["tab"] = "overview"
            st.rerun()


def _render_add_target_form() -> None:
    with st.expander("➕ Add target"):
        st.caption(
            "Just a name for now. Build your filters on otomoto.pl/autoplac.pl "
            "using their own search UI, then paste the resulting URL into "
            "this target's **Settings** tab."
        )
        with st.form("add_target_form", clear_on_submit=True):
            label = st.text_input("Label", placeholder="Volvo XC90 (2025+)")
            submitted = st.form_submit_button("Add", type="primary")
        if submitted:
            label = label.strip()
            if not label:
                st.error("Label is required.")
            else:
                key = _unique_key(_slugify(label))
                try:
                    store.upsert(key=key, label=label, sources=[])
                except TargetStoreError as exc:
                    st.error(str(exc))
                else:
                    st.cache_data.clear()
                    st.query_params["car"] = key
                    st.query_params["tab"] = "settings"
                    st.rerun()


def _render_grid(targets: list) -> None:
    render_nav()
    st.title("🚗 Car Tracker")
    if not targets:
        st.info("Nothing tracked yet - add your first target below.")
    else:
        cols_per_row = 2
        for row_start in range(0, len(targets), cols_per_row):
            row = targets[row_start : row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, t in zip(cols, row, strict=False):
                with col:
                    _render_card(t)
    st.divider()
    _render_add_target_form()

    stale = [m for m in models_with_data() if m not in {t["key"] for t in targets}]
    if stale:
        st.caption(
            f"{len(stale)} untracked model(s) still have data on disk: {', '.join(stale)}"
        )


# --------------------------------------------------------------------------
# Detail view (one target): Overview + Settings tabs
# --------------------------------------------------------------------------


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _load_editor_state(key: str, existing: dict) -> str:
    """Seed this target's sources row-editor list into session_state, once
    per key. Returns the session_state key. Rows carry a stable ``_id``
    (not their list index) so add/remove doesn't scramble other rows'
    widget state across reruns.
    """
    sk = f"{key}__sources"
    if sk not in st.session_state:
        raw_sources = existing.get("sources") or [{"site": "", "url": ""}]
        st.session_state[sk] = [
            {"_id": _new_id(), "site": s.get("site", ""), "url": s.get("url", "")}
            for s in raw_sources
        ]
    return sk


def _reset_editor_state(sk: str) -> None:
    st.session_state.pop(sk, None)


def _sources_editor(sk: str) -> None:
    st.markdown("**Sources**")
    st.caption(
        "One or more otomoto.pl / autoplac.pl search URLs, merged into one data "
        "file - use the sidebar's site button to (re)build filters on the "
        "site itself, then paste the URL here."
    )
    rows = st.session_state[sk]
    if rows:
        h1, h2, _ = st.columns([1, 3, 0.4])
        h1.caption("Site (optional)")
        h2.caption("URL")
    remove_at = None
    for i, row in enumerate(rows):
        c1, c2, c3 = st.columns([1, 3, 0.4])
        row["site"] = c1.text_input(
            "site",
            value=row["site"],
            key=f"{sk}_site_{row['_id']}",
            placeholder="otomoto",
            label_visibility="collapsed",
        )
        row["url"] = c2.text_input(
            "url",
            value=row["url"],
            key=f"{sk}_url_{row['_id']}",
            placeholder="https://www.otomoto.pl/osobowe/<make>/<model>",
            label_visibility="collapsed",
        )
        if c3.button("✕", key=f"{sk}_rm_{row['_id']}", help="Remove this source"):
            remove_at = i
    if remove_at is not None:
        rows.pop(remove_at)
        st.rerun()
    if st.button("➕ Add source", key=f"{sk}_add"):
        rows.append({"_id": _new_id(), "site": "", "url": ""})
        st.rerun()


def _build_sources(sk: str) -> list:
    out = []
    for row in st.session_state[sk]:
        url = row["url"].strip()
        if not url:
            continue
        entry = {"url": url}
        if row["site"].strip():
            entry["site"] = row["site"].strip()
        out.append(entry)
    return out


def _render_settings_tab(t: dict) -> None:
    key = t["key"]
    sk = _load_editor_state(key, t)

    label = st.text_input("Label", value=t["label"], key=f"{key}_label")
    note = st.text_input("Note (optional)", value=t.get("note", ""), key=f"{key}_note")

    _sources_editor(sk)

    col1, col2 = st.columns([1, 1])
    if col1.button("💾 Save changes", key=f"{key}_submit", type="primary"):
        try:
            store.upsert(
                key=key,
                label=label,
                sources=_build_sources(sk),
                note=note,
            )
        except TargetStoreError as exc:
            st.error(str(exc))
        else:
            _reset_editor_state(sk)
            st.cache_data.clear()
            st.success("Saved.")
            st.rerun()

    if col2.button("🗑️ Delete target", key=f"{key}_delete"):
        store.delete(key)
        _reset_editor_state(sk)
        st.cache_data.clear()
        st.query_params.clear()
        st.success(f"Deleted '{key}'.")
        st.rerun()


def _render_overview_tab(t: dict) -> None:
    key = t["key"]
    if not t.get("sources"):
        st.info("No otomoto URL yet - add one in the **Settings** tab.")
        return

    has_data = key in models_with_data()
    last_updated = load_metadata(key).get("last_updated", "") if has_data else ""
    caption = ""
    if last_updated:
        when = _relative_time(last_updated)
        stamp = last_updated[:16].replace("T", " ")
        caption = f"Last scraped: {stamp}" + (f" ({when})" if when else "")
    cap_col, btn_col = st.columns([5, 1])
    cap_col.caption(caption or "Not scraped yet.")
    if btn_col.button(
        "🔄 Update now",
        help="Scrapes every tracked target, not just this one",
        key=f"update_{key}",
    ):
        _trigger_update_now()
        load_model.clear()
        load_metadata.clear()
        st.rerun()

    if not has_data:
        st.info("No data yet - click 'Update now' above, or wait for the next scrape.")
        return

    df = load_model(key)
    if "active" not in df.columns:
        df["active"] = True
    active_only = st.checkbox("Active listings only", value=True, key=f"active_{key}")
    if active_only:
        df = _active_only(df)

    for col in ("year", "mileage", "current_price", "engine_power"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        st.info("No listings match the current filters.")
        return

    # Optional year filter when the data spans multiple years.
    if "year" in df.columns and df["year"].notna().any():
        ylo, yhi = int(df["year"].min()), int(df["year"].max())
        if yhi > ylo:
            lo, hi = st.slider("Year", ylo, yhi, (ylo, yhi), key=f"year_{key}")
            df = df[df["year"].between(lo, hi)]

    if df.empty:
        st.info("No listings match the current filters.")
        return

    # No origin/condition filter widgets by design: filtering what you track
    # belongs in the target's search URL (config), not a runtime UI layer on
    # top of already-scraped data - see "Origin filtering" in README. origin/
    # condition are still columns below, sortable by clicking the header.

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
    cols = [c for c in _COLUMN_LABELS if c in df.columns] + (
        ["url"] if "url" in df.columns else []
    )
    table = df[cols].sort_values("current_price", na_position="last")
    column_config = {
        field: st.column_config.Column(label) for field, label in _COLUMN_LABELS.items()
    }
    column_config["url"] = st.column_config.LinkColumn("Link", display_text="open")
    st.dataframe(table, width="stretch", hide_index=True, column_config=column_config)


def _render_detail(t: dict) -> None:
    def _sidebar_extra() -> None:
        if st.button("← All cars"):
            st.query_params.clear()
            st.rerun()
        sources = t.get("sources") or []
        if sources:
            for i, s in enumerate(sources):
                site_label = s.get("site") or (
                    f"source {i + 1}" if len(sources) > 1 else "otomoto"
                )
                st.link_button(f"🔗 {site_label}", s["url"], width="stretch")
        else:
            st.caption("No otomoto URL yet - add one in the Settings tab.")

    render_nav(_sidebar_extra)

    img_url = _target_image(t["key"])
    if img_url:
        img_col, title_col = st.columns([1, 9], vertical_alignment="center")
        img_col.image(img_url, width=90)
        title_col.title(t["label"])
    else:
        st.title(f"🚗 {t['label']}")
    overview_tab, settings_tab = st.tabs(["📊 Overview", "⚙️ Settings"])
    with overview_tab:
        _render_overview_tab(t)
    with settings_tab:
        _render_settings_tab(t)


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------

targets = store.list_targets()
targets_by_key = {t["key"]: t for t in targets}
selected_key = st.query_params.get("car")

if selected_key and selected_key in targets_by_key:
    _render_detail(targets_by_key[selected_key])
else:
    if selected_key:  # stale param (deleted target) - drop it, show the grid
        st.query_params.clear()
    _render_grid(targets)
