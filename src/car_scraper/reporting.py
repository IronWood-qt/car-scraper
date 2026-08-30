"""Reporting: static HTML dashboard + alert message formatting.

Pure-stdlib (json/pathlib/datetime/html) so it has no heavy dependencies and
can run anywhere the data files live. Two public helpers:

- ``build_static_report`` writes a self-contained ``index.html`` (Plotly via
  CDN, data baked inline) that the daily pipeline commits and GitHub Pages
  serves. It pre-computes the insightful bits in Python: a per-listing "deal
  score" (price vs an expected price from mileage + year), a reconstructed
  median-asking-price-over-time series, and per-model KPIs.
- ``format_alert_markdown`` turns a scrape run summary into a GitHub issue body.
"""

import html
import json
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

from src.facets import classify
from src.target_store import open_default_store


def _md_escape(s: str) -> str:
    """Escape characters that would break out of a markdown link/text."""
    return (s or "").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def _money(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " zł"
    except (TypeError, ValueError):
        return "—"


def _load_targets_list(db_path: str | None = None) -> list[dict]:
    """Raw target dicts from targets.db (empty if the store can't be opened).

    targets.db is gitignored (never committed - see README) so it may simply
    not exist yet, e.g. in a fresh checkout with nothing set up; that's not
    an error, just an empty target list. ``open_default_store`` auto-imports
    from a legacy targets.json the first time it's called, if one is present.
    """
    try:
        return open_default_store(db_path).list_targets()
    except OSError:
        return []


def load_targets(db_path: str | None = None) -> dict[str, str]:
    """Return ``{key: label}`` from targets.db (empty if missing)."""
    return {
        t["key"]: t.get("label", t["key"])
        for t in _load_targets_list(db_path)
        if t.get("key")
    }


def load_target_facets(db_path: str | None = None) -> dict[str, dict]:
    """Return ``{key: facets_config}`` for targets that define a "facets" block.

    This is what lets a target's variant/trim/body classification be
    configured entirely in targets.db - see :func:`facets.classify`
    and the dashboard's "Manage Targets" page.
    """
    return {
        t["key"]: t["facets"]
        for t in _load_targets_list(db_path)
        if t.get("key") and t.get("facets")
    }


def load_models(data_dir: str, db_path: str | None = None) -> list[dict]:
    """Load every model's listings from ``data_dir``.

    Each item: ``{"key", "label", "listings": [listing, ...], "facets_config"}``.
    """
    labels = load_targets(db_path)
    facets_configs = load_target_facets(db_path)
    base = Path(data_dir)
    models: list[dict] = []
    if not base.exists():
        return models
    for model_dir in sorted(base.iterdir()):
        if (
            not model_dir.is_dir()
            or model_dir.name.startswith(".")
            or model_dir.name == "plots"
        ):
            continue
        data_file = model_dir / f"{model_dir.name}.json"
        if not data_file.exists():
            continue
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "listings" in data:
            listings = list(data["listings"].values())
        elif isinstance(data, list):
            listings = data
        else:
            continue
        models.append(
            {
                "key": model_dir.name,
                "label": labels.get(model_dir.name, model_dir.name),
                "listings": listings,
                "facets_config": facets_configs.get(model_dir.name),
            }
        )
    return models


def _active(listing: dict) -> bool:
    return listing.get("active", True)


# --- analytics -------------------------------------------------------------


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Solve a small linear system by Gaussian elimination. None if singular."""
    n = len(matrix)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-9:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(n):
            if r == col:
                continue
            factor = a[r][col] / a[col][col]
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


def _ols(features: list[list[float]], ys: list[float]) -> list[float] | None:
    """Ordinary least squares with intercept. Returns coefficients or None.

    ``features`` is a list of feature-rows (no intercept column). Solves the
    normal equations (X'X)b = X'y.
    """
    rows = [[1.0] + f for f in features]
    k = len(rows[0])
    if len(rows) < k + 1:  # need more points than parameters
        return None
    xtx = [
        [sum(rows[r][i] * rows[r][j] for r in range(len(rows))) for j in range(k)]
        for i in range(k)
    ]
    xty = [sum(rows[r][i] * ys[r] for r in range(len(rows))) for i in range(k)]
    return _solve(xtx, xty)


def _deal_scores(listings: list[dict]) -> None:
    """Annotate each listing with predicted_price + deal_pct in place.

    Expected price is modelled (OLS) from mileage and, when there is enough
    spread, production year, fit over every listing passed in. ``deal_pct`` < 0
    means cheaper than expected (a deal).
    """
    pts = [
        car
        for car in listings
        if isinstance(car.get("current_price"), (int, float))
        and car["current_price"] > 0
        and isinstance(car.get("mileage"), (int, float))
    ]
    if len(pts) < 4:
        return
    years = {car.get("year") for car in pts if car.get("year")}
    use_year = len(years) >= 2 and all(car.get("year") for car in pts)
    feats = [
        [float(car["mileage"]) / 1000.0] + ([float(car["year"])] if use_year else [])
        for car in pts
    ]
    ys = [float(car["current_price"]) for car in pts]
    coef = _ols(feats, ys)
    if not coef:
        return
    for car, f in zip(pts, feats, strict=False):
        pred = coef[0] + sum(c * x for c, x in zip(coef[1:], f, strict=False))
        if pred > 0:
            car["predicted_price"] = round(pred)
            car["deal_pct"] = round((car["current_price"] - pred) / pred * 100, 1)


def _readings(listing: dict) -> list[list]:
    out = []
    for r in listing.get("price_readings") or []:
        if (
            isinstance(r, (list, tuple))
            and len(r) == 2
            and isinstance(r[1], (int, float))
            and r[1] > 0
        ):
            out.append([r[0], r[1]])
    return out


def _market_trend(listings: list[dict]) -> list[dict]:
    """Reconstruct median asking price per day across listings while active.

    For each day a listing was live (first_seen..last_seen) its price is the
    most recent reading up to that day. The daily median of those prices is a
    clean "what did the market ask" signal that grows as the pipeline runs.
    """
    spans = []
    overall_lo: date | None = None
    overall_hi: date | None = None
    for car in listings:
        readings = sorted(_readings(car), key=lambda r: r[0])
        if not readings:
            continue
        try:
            lo = datetime.strptime(car.get("first_seen", ""), "%Y-%m-%d").date()
            hi = datetime.strptime(car.get("last_seen", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if hi < lo:
            lo, hi = hi, lo
        daily = [(datetime.fromtimestamp(ts).date(), p) for ts, p in readings]
        spans.append((lo, hi, daily))
        overall_lo = lo if overall_lo is None else min(overall_lo, lo)
        overall_hi = hi if overall_hi is None else max(overall_hi, hi)
    if not spans or overall_lo is None or overall_hi is None:
        return []
    span_days = (overall_hi - overall_lo).days
    step = 7 if span_days > 180 else 1  # weekly buckets for long histories
    series = []
    day = overall_lo
    while day <= overall_hi:
        prices = []
        for lo, hi, daily in spans:
            if lo <= day <= hi:
                price = None
                for d, p in daily:
                    if d <= day:
                        price = p
                    else:
                        break
                if price is None and daily:
                    price = daily[0][1]
                if price:
                    prices.append(price)
        if prices:
            series.append(
                {
                    "date": day.isoformat(),
                    "median": int(statistics.median(prices)),
                    "count": len(prices),
                }
            )
        day += timedelta(days=step)
    return series


def _has_drop(listing: dict) -> bool:
    r = _readings(listing)
    return len(r) >= 2 and r[-1][1] < r[-2][1]


_KEEP = (
    "internal_id",
    "title",
    "version",
    "year",
    "mileage",
    "current_price",
    "engine_power",
    "engine_capacity",
    "fuel_type",
    "gearbox",
    "url",
    "price_readings",
    "predicted_price",
    "deal_pct",
    "active",
    "first_seen",
    "last_seen",
)


def _prep_model(model: dict) -> dict:
    """Build the slim, analytics-enriched payload for one model.

    Ships *all* listings (each tagged ``active`` and ``facets``) so the
    dashboard can switch the working set client-side: the "show historical"
    toggle and the per-dimension facet chips both filter in the browser. The
    deal model is fit on the full history (more data = a more stable expected
    price). The market trend is recomputed in JS from whatever the working set
    is, so it reacts to the toggle and the facet filters too — it mirrors
    :func:`_market_trend` (kept here as the tested reference implementation).
    """
    listings = model["listings"]
    _deal_scores(listings)
    key = model["key"]
    facets_config = model.get("facets_config")

    def slim(listing):
        out = {k: listing.get(k) for k in _KEEP}
        out["active"] = _active(listing)
        out["facets"] = classify(key, listing, config=facets_config)
        return out

    slimmed = [slim(car) for car in listings]

    # label->flag map so origin chips show the right flag. The chip value lists
    # themselves are derived client-side from the listings (so a dimension can
    # carry an explicit "Unknown" bucket for cars that predate a field), which
    # keeps every dimension's chip counts reconciling to the working-set size.
    flags = {
        f["country"]: f["flag"]
        for car in slimmed
        if (f := car["facets"]).get("country") and f.get("flag")
    }

    return {
        "key": key,
        "label": model["label"],
        "listings": slimmed,
        "flags": flags,
    }


# --- markdown alerts -------------------------------------------------------


def format_alert_markdown(new: list[dict], drops: list[dict], date: str) -> str:
    """Format new listings + price drops as a markdown alert body."""
    lines = [f"## 🚗 Car alerts — {date}", ""]
    if new:
        lines.append(f"### 🆕 {len(new)} new listing(s)")
        for item in new:
            label = item.get("_model_label", item.get("model", ""))
            title = _md_escape(item.get("title", "Listing"))
            url = item.get("url", "")
            bits = []
            if item.get("year"):
                bits.append(str(item["year"]))
            if item.get("mileage") is not None:
                bits.append(f"{int(item['mileage']):,} km".replace(",", " "))
            if item.get("engine_power"):
                bits.append(f"{item['engine_power']} KM")
            if item.get("gearbox"):
                bits.append(item["gearbox"])
            meta = " · ".join(bits)
            price = _money(item.get("current_price") or item.get("price"))
            lines.append(f"- **{label}** — [{title}]({url}) — {meta} — **{price}**")
        lines.append("")
    if drops:
        lines.append(f"### 📉 {len(drops)} price drop(s)")
        for d in drops:
            item = d["listing"]
            label = item.get("_model_label", item.get("model", ""))
            title = _md_escape(item.get("title", "Listing"))
            url = item.get("url", "")
            old, new_p = d["old_price"], d["new_price"]
            pct = (new_p - old) / old * 100 if old else 0
            lines.append(
                f"- **{label}** — [{title}]({url}) — "
                f"{_money(old)} → **{_money(new_p)}** ({pct:+.1f}%)"
            )
        lines.append("")
    if not new and not drops:
        lines.append("_No new listings or price drops._")
    return "\n".join(lines)


def format_alert_pushover(
    new: list[dict], drops: list[dict], date: str
) -> tuple[str, str]:
    """``(title, message)`` compact plain-text summary for a Pushover push.

    Pushover caps messages at 1024 chars and doesn't render markdown, so this
    lists at most a handful of items per section and points at the full
    detail (dashboard / GitHub issue) for the rest.
    """
    title = f"🚗 {len(new)} new, {len(drops)} price drop(s) — {date}"
    lines = []
    for item in new[:5]:
        label = item.get("_model_label", item.get("model", ""))
        price = _money(item.get("current_price") or item.get("price"))
        lines.append(f"NEW  {label}: {price}")
    for d in drops[:5]:
        item = d["listing"]
        label = item.get("_model_label", item.get("model", ""))
        old, new_p = d["old_price"], d["new_price"]
        lines.append(f"DROP {label}: {_money(old)} -> {_money(new_p)}")
    shown = min(len(new), 5) + min(len(drops), 5)
    remaining = len(new) + len(drops) - shown
    if remaining > 0:
        lines.append(f"...and {remaining} more, see dashboard / GitHub issue")
    message = "\n".join(lines) or "No details"
    return title, message[:1024]


# --- static HTML -----------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).with_name("report_template.html")


def build_static_report(
    data_dir: str = "data",
    out_path: str = "plots/index.html",
    db_path: str | None = None,
    generated: str = "",
) -> str:
    """Write a self-contained HTML dashboard. Returns the output path."""
    models = [_prep_model(m) for m in load_models(data_dir, db_path)]
    all_listings = [car for m in models for car in m["listings"]]
    active = [car for car in all_listings if car.get("active")]
    global_data = {
        "generated": generated or "now",
        "models": len(models),
        "active": len(active),
        "total": len(all_listings),
        "drops": sum(1 for car in active if _has_drop(car)),
    }
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    out_html = (
        template.replace("__GENERATED__", html.escape(generated or "now"))
        .replace("__GLOBAL_JSON__", json.dumps(global_data, ensure_ascii=False))
        .replace("__MODELS_JSON__", json.dumps(models, ensure_ascii=False, default=str))
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_html, encoding="utf-8")
    return str(out)


def _selfcheck() -> None:
    """Assert-based check of the alert + analytics logic."""
    md = format_alert_markdown(
        new=[
            {
                "_model_label": "Supra",
                "title": "Toyota Supra",
                "url": "http://x",
                "year": 2022,
                "mileage": 9200,
                "engine_power": 340,
                "gearbox": "manual",
                "current_price": 240000,
            }
        ],
        drops=[
            {
                "listing": {
                    "_model_label": "LC",
                    "title": "Lexus LC",
                    "url": "http://y",
                },
                "old_price": 400000,
                "new_price": 380000,
            }
        ],
        date="2026-06-19",
    )
    assert "1 new listing" in md and "240 000 zł" in md and "-5.0%" in md, md
    assert _md_escape("Car](evil)") == "Car\\](evil)"

    title, message = format_alert_pushover(
        new=[{"_model_label": "Supra", "current_price": 240000}],
        drops=[
            {
                "listing": {"_model_label": "LC"},
                "old_price": 400000,
                "new_price": 380000,
            }
        ],
        date="2026-06-19",
    )
    assert "1 new, 1 price drop" in title, title
    assert "NEW  Supra: 240 000 zł" in message and "DROP LC:" in message, message
    assert len(message) <= 1024

    # OLS recovers a known linear relation: price = 100000 - 2*mileage(k) + ...
    coef = _ols([[10.0], [20.0], [30.0], [40.0]], [80.0, 60.0, 40.0, 20.0])
    assert coef and abs(coef[1] - (-2.0)) < 1e-6, coef

    # Deal scoring flags the underpriced car as the best deal.
    active = [
        {"current_price": 300000, "mileage": 20000, "year": 2019},
        {"current_price": 280000, "mileage": 40000, "year": 2019},
        {"current_price": 260000, "mileage": 60000, "year": 2019},
        {"current_price": 200000, "mileage": 25000, "year": 2019},  # clearly cheap
        {"current_price": 240000, "mileage": 80000, "year": 2019},
    ]
    _deal_scores(active)
    assert active[3]["deal_pct"] < 0, active[3]

    # Market trend carries a stable price forward across the active window and
    # takes the daily median. One listing at 100k over 2 days -> 2 points @ 100k.
    ts = int(datetime(2025, 1, 1).timestamp())
    trend = _market_trend(
        [
            {
                "first_seen": "2025-01-01",
                "last_seen": "2025-01-02",
                "price_readings": [[ts, 100000]],
            }
        ]
    )
    assert [p["median"] for p in trend] == [100000, 100000], trend
    print("reporting self-check OK")


if __name__ == "__main__":
    _selfcheck()
