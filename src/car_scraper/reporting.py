"""Alert message formatting: turns a scrape run summary into the two alert
shapes scrape-all sends - a GitHub issue body (markdown) and a compact
Pushover push (plain text, 1024-char cap). Pure-stdlib, no heavy dependencies.
"""


def _md_escape(s: str) -> str:
    """Escape characters that would break out of a markdown link/text."""
    return (s or "").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def _money(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " zł"
    except (TypeError, ValueError):
        return "—"


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


def _selfcheck() -> None:
    """Assert-based check of the alert formatting."""
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

    print("reporting self-check OK")


if __name__ == "__main__":
    _selfcheck()
