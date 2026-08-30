"""Manage Targets: add/edit/delete tracked cars, stored in targets.db.

Replaces hand-editing targets.json. Same sys.path setup as app.py - see the
comment there for why (must mirror dashboard/'s position relative to src/ in
dashboard/Dockerfile too).
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.target_store import TargetStoreError, open_default_store  # noqa: E402

DB_PATH = os.environ.get("TARGETS_DB")

st.set_page_config(page_title="Manage Targets", page_icon="🎯", layout="wide")
st.title("🎯 Manage Targets")
st.caption(
    "Which cars get tracked - stored in targets.db, never committed to git. "
    "Edits here take effect on the next `scrape-all` run."
)

store = open_default_store(DB_PATH)


def _clear_dashboard_cache() -> None:
    """Bust app.py's cached label lookup so edits show up immediately."""
    st.cache_data.clear()


_SOURCES_PLACEHOLDER = json.dumps(
    [{"site": "otomoto", "url": "https://www.otomoto.pl/osobowe/<make>/<model>"}],
    indent=2,
)
_FACETS_PLACEHOLDER = json.dumps(
    {"variant": [{"label": "T8", "keywords": ["t8", "recharge"]}]}, indent=2
)


def _target_form(existing: dict | None) -> None:
    """Render the add/edit form for one target. ``existing=None`` -> add-new."""
    is_new = existing is None
    prefix = "new" if is_new else existing["key"]

    key = st.text_input(
        "Key",
        value="" if is_new else existing["key"],
        disabled=not is_new,
        help="Lowercase letters/digits/hyphens, e.g. 'make-model'. Can't be changed after creation.",
        key=f"{prefix}_key",
    )
    label = st.text_input(
        "Label",
        value="" if is_new else existing["label"],
        help="Shown in the dashboard and alerts.",
        key=f"{prefix}_label",
    )
    note = st.text_input(
        "Note (optional)",
        value="" if is_new else existing.get("note", ""),
        key=f"{prefix}_note",
    )
    sources_text = st.text_area(
        "Sources (JSON array)",
        value=_SOURCES_PLACEHOLDER
        if is_new
        else json.dumps(existing["sources"], indent=2, ensure_ascii=False),
        height=140,
        help='One or more {"url": "..."} entries (otomoto.pl / autoplac.pl search URLs). '
        "'site' is optional/for your own reference.",
        key=f"{prefix}_sources",
    )
    facets_text = st.text_area(
        "Facets (JSON object, optional)",
        value=""
        if is_new
        else (
            json.dumps(existing["facets"], indent=2, ensure_ascii=False)
            if existing.get("facets")
            else ""
        ),
        height=140,
        placeholder=_FACETS_PLACEHOLDER,
        help="Turns variant/trim/body into dashboard filter chips. Leave blank for none. "
        "Each dimension is an ordered list of {label, keywords} rules, first match wins.",
        key=f"{prefix}_facets",
    )

    button_label = "➕ Add target" if is_new else "💾 Save changes"
    col1, col2 = st.columns([1, 1])
    if col1.button(button_label, key=f"{prefix}_submit", type="primary"):
        try:
            sources = json.loads(sources_text) if sources_text.strip() else []
            facets = json.loads(facets_text) if facets_text.strip() else None
        except json.JSONDecodeError as exc:
            st.error(f"Invalid JSON: {exc}")
            return
        try:
            store.upsert(
                key=key, label=label, sources=sources, note=note, facets=facets
            )
        except TargetStoreError as exc:
            st.error(str(exc))
            return
        _clear_dashboard_cache()
        st.success(f"Saved '{key}'.")
        st.rerun()

    if not is_new and col2.button("🗑️ Delete", key=f"{prefix}_delete"):
        store.delete(existing["key"])
        _clear_dashboard_cache()
        st.success(f"Deleted '{existing['key']}'.")
        st.rerun()


targets = store.list_targets()

st.subheader(f"Tracked ({len(targets)})")
if not targets:
    st.info("Nothing tracked yet - add one below, or import targets.example.json.")
else:
    st.dataframe(
        [
            {
                "key": t["key"],
                "label": t["label"],
                "sources": len(t["sources"]),
                "facets": "✓" if t.get("facets") else "",
                "note": t.get("note", ""),
            }
            for t in targets
        ],
        width="stretch",
        hide_index=True,
    )
    for t in targets:
        with st.expander(f"✏️ {t['label']} ({t['key']})"):
            _target_form(t)

st.subheader("➕ Add a target")
with st.expander("New target", expanded=len(targets) == 0):
    _target_form(None)

st.subheader("📥 Import from a JSON file")
st.caption(
    "Bulk-load targets from a targets.json-shaped file (e.g. targets.example.json). "
    "Existing keys are skipped unless you check overwrite."
)
uploaded = st.file_uploader("Choose a .json file", type="json", key="import_file")
overwrite = st.checkbox("Overwrite existing keys", key="import_overwrite")
if uploaded is not None and st.button("Import"):
    tmp_path = Path("/tmp") / f"targets_import_{uploaded.name}"  # noqa: S108 - local-only tool
    tmp_path.write_bytes(uploaded.getvalue())
    try:
        n = store.import_json(tmp_path, overwrite=overwrite)
    except (json.JSONDecodeError, TargetStoreError) as exc:
        st.error(f"Import failed: {exc}")
    else:
        _clear_dashboard_cache()
        st.success(f"Imported {n} target(s).")
        st.rerun()
    finally:
        tmp_path.unlink(missing_ok=True)
