"""Otomoto search-page scraper.

Reads the structured listing data that otomoto.pl embeds in the search page's
Next.js ``__NEXT_DATA__`` (urql / GraphQL cache). Every listing on a search
results page carries clean, typed fields there: price as an integer, plus
``year``, ``mileage``, ``fuel_type``, ``gearbox``, ``engine_power``,
``engine_capacity`` and ``version``.

This replaces the old approach of fetching every individual advert page and
regex-scraping its HTML, which produced corrupt prices (digits concatenated
from unrelated elements) and bogus years (the first 1990-2024 number anywhere
on the page). One search request now yields fully-typed data for ~32 cars.
"""

import contextlib
import json
import re
import time

import httpx

from src.car_scraper.utils.logger import logger

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
}


def _find_search_result(obj: object) -> dict | None:
    """Recursively locate the advertSearch result (has ``edges`` + ``pageInfo``)."""
    if isinstance(obj, dict):
        if "edges" in obj and isinstance(obj["edges"], list) and "pageInfo" in obj:
            return obj
        for value in obj.values():
            found = _find_search_result(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_search_result(value)
            if found is not None:
                return found
    return None


def _node_to_listing(node: dict) -> dict | None:
    """Convert a GraphQL Advert node into a flat listing dict."""
    listing_id = node.get("id")
    if not listing_id:
        return None

    params = {p.get("key"): p for p in node.get("parameters", []) if p.get("key")}

    def num(key: str) -> int | None:
        p = params.get(key)
        if not p:
            return None
        try:
            return int(p["value"])
        except (ValueError, TypeError, KeyError):
            return None

    def val(key: str) -> str | None:
        p = params.get(key)
        return p.get("value") if p else None

    price = None
    with contextlib.suppress(KeyError, TypeError, ValueError):
        price = int(node["price"]["amount"]["units"])
    if price is not None and price <= 0:
        price = None  # treat 0 / negative as missing

    location = None
    with contextlib.suppress(KeyError, TypeError):
        location = node["location"]["city"]["name"]

    def disp(key: str) -> str | None:
        p = params.get(key)
        return p.get("displayValue") if p else None

    image_url = None
    with contextlib.suppress(KeyError, TypeError):
        thumb = node.get("thumbnail") or {}
        image_url = thumb.get("x2") or thumb.get("x1")

    return {
        "id": str(listing_id),
        "title": node.get("title", ""),
        "version": disp("version"),
        "short_description": (node.get("shortDescription") or "").strip() or None,
        "url": node.get("url", ""),
        "image_url": image_url,
        "price": price,
        "year": num("year"),
        "mileage": num("mileage"),
        "fuel_type": val("fuel_type"),
        "gearbox": val("gearbox"),
        "engine_power": num("engine_power"),
        "engine_capacity": num("engine_capacity"),
        "country": val("country_origin"),  # otomoto code: pl/d/usa/cdn/f/s...
        "country_label": disp("country_origin"),  # e.g. "Stany Zjednoczone"
        "location": location,
        "created_at": node.get("createdAt"),
    }


def parse_listings(html: str) -> tuple[list[dict], int | None]:
    """Parse listings + total count from a search page's HTML.

    Returns ``(listings, total_count)``. ``total_count`` is ``None`` if the
    page could not be parsed (e.g. layout change or anti-bot page).
    """
    match = _NEXT_DATA_RE.search(html)
    if not match:
        logger.warning("No __NEXT_DATA__ found on search page (layout change?)")
        return [], None

    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse __NEXT_DATA__ JSON: {exc}")
        return [], None

    urql = next_data.get("props", {}).get("pageProps", {}).get("urqlState", {})
    result = None
    for entry in urql.values():
        data = entry.get("data")
        if not data:
            continue
        try:
            data = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            continue
        result = _find_search_result(data)
        if result is not None:
            break

    if result is None:
        return [], None

    total_count = result.get("totalCount")
    listings = []
    for edge in result.get("edges", []):
        node = edge.get("node", {})
        if node.get("__typename") != "Advert":
            continue  # skip promoted/banner slots
        listing = _node_to_listing(node)
        if listing:
            listings.append(listing)
    return listings, total_count


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
        logger.error(f"Error fetching search page {page}: {exc}")
        return None


def scrape_search(
    search_url: str,
    max_pages: int = 10,
    page_size: int = 32,
    delay: float = 0.5,
) -> list[dict]:
    """Scrape all listings for a search URL across pages.

    Args:
        search_url: otomoto search URL (may already contain filter params).
        max_pages: hard cap on pages fetched.
        page_size: otomoto results per page (used to compute page count).
        delay: seconds to sleep between page fetches.

    Returns:
        Deduplicated list of clean listing dicts.
    """
    logger.info(f"Scraping search: {search_url}")
    html = fetch_search_page(search_url, 1)
    if html is None:
        return []

    listings, total = parse_listings(html)
    by_id: dict[str, dict] = {x["id"]: x for x in listings}

    pages_needed = (total + page_size - 1) // page_size if total else 1
    pages_needed = min(pages_needed, max_pages)
    logger.info(f"Found {total} listings (~{pages_needed} pages, cap {max_pages})")

    for page in range(2, pages_needed + 1):
        time.sleep(delay)
        html = fetch_search_page(search_url, page)
        if html is None:
            continue
        page_listings, _ = parse_listings(html)
        if not page_listings:
            break
        for listing in page_listings:
            by_id[listing["id"]] = listing

    result = list(by_id.values())
    logger.info(f"Scraped {len(result)} unique listings")
    return result
