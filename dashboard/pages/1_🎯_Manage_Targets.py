"""Manage Targets: add/edit/delete tracked cars, stored in targets.db.

Replaces hand-editing targets.json. Same sys.path setup as 🚗_Dashboard.py -
see the comment there for why (must mirror dashboard/'s position relative to
src/ in dashboard/Dockerfile too).
"""

import os
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.target_store import TargetStoreError, open_default_store  # noqa: E402

DB_PATH = os.environ.get("TARGETS_DB")
_DIMENSIONS = ("variant", "trim", "body")
_DIM_LABELS = {
    "variant": "Variant (e.g. engine/powertrain)",
    "trim": "Trim",
    "body": "Body style",
}

st.set_page_config(page_title="Manage Targets", page_icon="🎯", layout="wide")
st.title("🎯 Manage Targets")
st.caption(
    "Which cars get tracked - stored in targets.db, never committed to git. "
    "Edits here take effect on the next `scrape-all` run."
)

store = open_default_store(DB_PATH)


def _clear_dashboard_cache() -> None:
    """Bust 🚗_Dashboard.py's cached label lookup so edits show up immediately."""
    st.cache_data.clear()


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _load_editor_state(prefix: str, existing: dict | None) -> tuple[str, str]:
    """Seed this target's row-editor lists into session_state, once per prefix.

    Returns the (sources_key, facets_key) into st.session_state. Rows carry a
    stable ``_id`` (not their list index) so add/remove doesn't scramble
    other rows' widget state across reruns.
    """
    sk, fk = f"{prefix}__sources", f"{prefix}__facets"
    if sk not in st.session_state:
        raw_sources = (existing or {}).get("sources") or [{"site": "", "url": ""}]
        st.session_state[sk] = [
            {"_id": _new_id(), "site": s.get("site", ""), "url": s.get("url", "")}
            for s in raw_sources
        ]
    if fk not in st.session_state:
        raw_facets = (existing or {}).get("facets") or {}
        st.session_state[fk] = {
            dim: [
                {
                    "_id": _new_id(),
                    "label": rule.get("label", ""),
                    "keywords": ", ".join(rule.get("keywords", [])),
                }
                for rule in raw_facets.get(dim, [])
            ]
            for dim in _DIMENSIONS
        }
    return sk, fk


def _reset_editor_state(sk: str, fk: str) -> None:
    st.session_state.pop(sk, None)
    st.session_state.pop(fk, None)


def _sources_editor(sk: str) -> None:
    st.markdown("**Sources**")
    st.caption(
        "One or more otomoto.pl / autoplac.pl search URLs, merged into one data file."
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


def _facets_editor(fk: str) -> None:
    st.markdown("**Facets** (optional filter chips)")
    st.caption(
        "Turns a variant/trim/body into a dashboard filter chip - no code needed. "
        "Rules are checked top to bottom, first keyword match wins, so put more "
        "specific labels first. Leave a dimension empty to skip it."
    )
    for dim in _DIMENSIONS:
        rows = st.session_state[fk][dim]
        with st.expander(_DIM_LABELS[dim], expanded=bool(rows)):
            if rows:
                h1, h2, _ = st.columns([1, 2, 0.4])
                h1.caption("Label")
                h2.caption("Keywords (comma-separated)")
            remove_at = None
            for i, row in enumerate(rows):
                c1, c2, c3 = st.columns([1, 2, 0.4])
                row["label"] = c1.text_input(
                    "label",
                    value=row["label"],
                    key=f"{fk}_{dim}_label_{row['_id']}",
                    placeholder="T8",
                    label_visibility="collapsed",
                )
                row["keywords"] = c2.text_input(
                    "keywords",
                    value=row["keywords"],
                    key=f"{fk}_{dim}_kw_{row['_id']}",
                    placeholder="t8, recharge",
                    label_visibility="collapsed",
                )
                if c3.button(
                    "✕", key=f"{fk}_{dim}_rm_{row['_id']}", help="Remove this rule"
                ):
                    remove_at = i
            if remove_at is not None:
                rows.pop(remove_at)
                st.rerun()
            if st.button(f"➕ Add {dim} rule", key=f"{fk}_{dim}_add"):
                rows.append({"_id": _new_id(), "label": "", "keywords": ""})
                st.rerun()


def _build_sources(sk: str) -> list[dict]:
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


def _build_facets(fk: str) -> dict | None:
    facets: dict = {}
    for dim in _DIMENSIONS:
        rules = []
        for row in st.session_state[fk][dim]:
            label = row["label"].strip()
            keywords = [w.strip() for w in row["keywords"].split(",") if w.strip()]
            if label and keywords:
                rules.append({"label": label, "keywords": keywords})
        if rules:
            facets[dim] = rules
    return facets or None


def _target_form(existing: dict | None) -> None:
    """Render the add/edit form for one target. ``existing=None`` -> add-new."""
    is_new = existing is None
    prefix = "new" if is_new else existing["key"]
    sk, fk = _load_editor_state(prefix, existing)

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

    _sources_editor(sk)
    _facets_editor(fk)

    button_label = "➕ Add target" if is_new else "💾 Save changes"
    col1, col2 = st.columns([1, 1])
    if col1.button(button_label, key=f"{prefix}_submit", type="primary"):
        sources = _build_sources(sk)
        if not sources:
            st.error("At least one source with a URL is required.")
            return
        try:
            store.upsert(
                key=key,
                label=label,
                sources=sources,
                note=note,
                facets=_build_facets(fk),
            )
        except TargetStoreError as exc:
            st.error(str(exc))
            return
        _reset_editor_state(sk, fk)
        _clear_dashboard_cache()
        st.success(f"Saved '{key}'.")
        st.rerun()

    if not is_new and col2.button("🗑️ Delete", key=f"{prefix}_delete"):
        store.delete(existing["key"])
        _reset_editor_state(sk, fk)
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
    except (ValueError, TargetStoreError) as exc:
        st.error(f"Import failed: {exc}")
    else:
        _clear_dashboard_cache()
        st.success(f"Imported {n} target(s).")
        st.rerun()
    finally:
        tmp_path.unlink(missing_ok=True)
