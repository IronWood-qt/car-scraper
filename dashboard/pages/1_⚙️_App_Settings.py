"""App Settings: global runtime knobs that used to be CLI flags / .env-only,
editable here instead - stored in targets.db (see src/settings_store.py).
Per-car config (which URLs to scrape, facets) lives on that car's own
Settings tab in 🚗_Dashboard.py, not here. Same sys.path setup as
🚗_Dashboard.py, see the comment there for why.
"""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.settings_store import SettingsStore  # noqa: E402

DB_PATH = os.environ.get("TARGETS_DB")

st.set_page_config(page_title="App Settings", page_icon="⚙️", layout="wide")
st.markdown(
    "<style>div.block-container{padding-top:2rem;}</style>", unsafe_allow_html=True
)
st.title("⚙️ App Settings")
st.caption(
    "Global scraper/alert config - stored in targets.db, never committed to "
    "git. Most changes apply on the next scrape - the scraper container's "
    "loop re-reads its interval each cycle, no restart needed. To add or "
    "edit which cars are tracked, open a card on the main dashboard and use "
    "its Settings tab."
)

store = SettingsStore(DB_PATH)
current = store.all()

with st.form("settings_form"):
    st.subheader("Scraping")
    max_pages = st.number_input(
        "Max pages per target",
        min_value=1,
        max_value=100,
        value=current["max_pages"],
        help="Passed to each target's search as the page-fetch cap during scrape-all.",
    )
    scrape_interval_hours = st.number_input(
        "Scraper loop interval (hours)",
        min_value=0.1,
        value=current["scrape_interval_seconds"] / 3600,
        step=0.5,
        help="How often the docker-compose 'scraper' container re-runs scrape-all. "
        "Not used if you're scheduling scrape-all yourself (host cron/systemd).",
    )

    st.subheader("Alerts")
    pushover_token = st.text_input(
        "Pushover application token",
        value=current["pushover_token"],
        type="password",
        help="From pushover.net. Falls back to the PUSHOVER_TOKEN env var if left blank.",
    )
    pushover_user = st.text_input(
        "Pushover user/group key",
        value=current["pushover_user"],
        type="password",
        help="Falls back to the PUSHOVER_USER env var if left blank.",
    )
    dashboard_url = st.text_input(
        "Dashboard URL",
        value=current["dashboard_url"],
        placeholder="http://192.168.1.50:8501",
        help="Linked from Pushover alerts. Falls back to the DASHBOARD_URL env var if left blank.",
    )

    submitted = st.form_submit_button("💾 Save", type="primary")

if submitted:
    store.set("max_pages", int(max_pages))
    store.set("scrape_interval_seconds", int(scrape_interval_hours * 3600))
    store.set("pushover_token", pushover_token.strip())
    store.set("pushover_user", pushover_user.strip())
    store.set("dashboard_url", dashboard_url.strip())
    st.success("Saved.")
    st.rerun()
