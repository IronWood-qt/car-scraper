"""autoplac.pl search-page scraper.

autoplac renders its search results server-side into an Angular *TransferState*
blob — a ``<script type="application/json">`` dictionary keyed by the API URL
that produced each fragment. We read the ``offers/search`` entry's
``offerList`` straight from that blob (same idea as the otomoto scraper, just a
different embedding) and emit the **same** flat listing dicts, so both sources
merge into one per-model data file for more datapoints.

Two quirks vs otomoto:

- engine power is stored in kW (``enginePowerKW``); we convert to KM (metric hp)
  to match otomoto.
- there is no country-of-origin field, only seller location — which is not the
  same thing — so ``country`` is left empty and origin is derived downstream by
  the text/Poland-default heuristic in :mod:`facets`.
"""

import json
import re
import time
from datetime import datetime

import httpx

from src.car_scraper.utils.logger import logger

_BASE = "https://autoplac.pl"
_KW_TO_KM = 1.35962  # 1 kW = 1.35962 metric horsepower (KM)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
}

_JSON_BLOB_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S
)

# autoplac enum -> the otomoto-style codes the rest of the pipeline expects.
_FUEL = {
    "GASOLINE": "petrol",
    "PETROL": "petrol",
    "DIESEL": "diesel",
    "HYBRID": "hybrid",
    "PLUGIN_HYBRID": "hybrid",
    "PLUG_IN_HYBRID": "hybrid",
    "MILD_HYBRID": "hybrid",
    "ELECTRIC": "electric",
    "LPG": "lpg",
}
_GEAR = {"Manualna": "manual", "Automatyczna": "automatic"}


def _find_offer_search(data: dict) -> dict | None:
    """Locate the offers/search response body (has an ``offerList``)."""
    for key, value in data.items():
        if ("offers/search" in key or key == "offer-response") and isinstance(
            value, dict
        ):
            body = value.get("body")
            if isinstance(body, dict) and isinstance(body.get("offerList"), list):
                return body
    return None


def _iso(ms: object) -> str | None:
    """Epoch milliseconds -> ISO string (None if unusable)."""
    if not isinstance(ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _offer_to_listing(item: dict) -> dict | None:
    """Convert one autoplac offer wrapper into a flat listing dict."""
    off = item.get("offer") or {}
    offer_id = off.get("id")
    if not offer_id:
        return None

    price = None
    try:
        price = int(off["priceInfo"]["primary"]["price"])
    except (KeyError, TypeError, ValueError):
        price = None
    if price is not None and price <= 0:
        price = None

    kw = off.get("enginePowerKW")
    power = round(kw * _KW_TO_KM) if isinstance(kw, (int, float)) and kw > 0 else None

    web = off.get("webUrl") or ""
    url = web if web.startswith("http") else f"{_BASE}{web}"

    version = off.get("version")
    if version in ("Inny", "Inna", ""):  # autoplac's "Other" -> no useful trim
        version = None

    city = off.get("city")
    return {
        "id": f"autoplac-{offer_id}",  # prefixed so it never collides with otomoto
        "title": off.get("title", ""),
        "version": version,
        "short_description": None,  # not present in the search payload
        "url": url,
        "price": price,
        "year": off.get("productionYear"),
        "mileage": off.get("mileage"),
        "fuel_type": _FUEL.get(
            off.get("fuelType") or "", off.get("fuelTypeText") or None
        ),
        "gearbox": _GEAR.get(
            off.get("transmissionTypeText") or "", off.get("transmissionTypeText")
        ),
        "engine_power": power,
        "engine_capacity": off.get("engineCapacity"),
        "country": None,  # autoplac exposes seller location, not country of origin
        "country_label": None,
        "location": city.title() if isinstance(city, str) else None,
        "created_at": _iso(off.get("insertTime")),
    }


def parse_listings(html: str) -> tuple[list[dict], int | None]:
    """Parse listings + total count from a search page's HTML.

    Returns ``(listings, total_count)``; ``total_count`` is ``None`` if the
    page could not be parsed (layout change or anti-bot page).
    """
    blobs = _JSON_BLOB_RE.findall(html)
    if not blobs:
        logger.warning("No application/json blob on autoplac page (layout change?)")
        return [], None
    for blob in sorted(blobs, key=len, reverse=True):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        body = _find_offer_search(data)
        if body is None:
            continue
        listings = [
            listing
            for offer in body["offerList"]
            if (listing := _offer_to_listing(offer)) is not None
        ]
        return listings, body.get("offerCount")
    return [], None


def fetch_search_page(url: str, page: int, timeout: int = 30) -> str | None:
    """Fetch one search results page (1-indexed)."""
    if page > 1:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}page={page}"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001 - network errors are expected/logged
        logger.error(f"Error fetching autoplac page {page}: {exc}")
        return None


def scrape_autoplac(
    search_url: str,
    max_pages: int = 10,
    page_size: int = 20,
    delay: float = 0.5,
) -> list[dict]:
    """Scrape all listings for an autoplac search URL across pages."""
    logger.info(f"Scraping autoplac search: {search_url}")
    html = fetch_search_page(search_url, 1)
    if html is None:
        return []

    listings, total = parse_listings(html)
    by_id: dict[str, dict] = {x["id"]: x for x in listings}

    pages_needed = (total + page_size - 1) // page_size if total else 1
    pages_needed = min(pages_needed, max_pages)
    logger.info(
        f"Found {total} autoplac listings (~{pages_needed} pages, cap {max_pages})"
    )

    for page in range(2, pages_needed + 1):
        time.sleep(delay)
        html = fetch_search_page(search_url, page)
        if html is None:
            continue
        page_listings, _ = parse_listings(html)
        if not page_listings:
            break
        before = len(by_id)
        for listing in page_listings:
            by_id[listing["id"]] = listing
        if len(by_id) == before:  # page returned nothing new -> stop paginating
            break

    result = list(by_id.values())
    logger.info(f"Scraped {len(result)} unique autoplac listings")
    return result
