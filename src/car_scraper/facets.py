"""Derive filterable facets (engine variant, trim, body style, origin) from a
listing's free-text + structured fields.

Pure keyword/regex heuristics — runs in the daily pipeline with no LLM and no
network. otomoto's structured ``version`` parameter is often blank, but the
free-text ``title`` + ``short_description`` carry the trim/body keywords
("Superturismo Carbon", "Inspiration Series", "RF", "Cabrio"), so we classify
from all three combined.

The dashboard turns each facet dimension into a row of filter chips; selecting
chips narrows the working set fed to every chart, KPI and the table.
"""

import difflib
import re
import unicodedata

# otomoto stores country of origin as the old international vehicle-registration
# code (D=Germany, F=France, ...), not ISO. Map the ones that show up on Polish
# imports to a flag; unknown codes just render without one.
_FLAGS = {
    "pl": "🇵🇱",
    "d": "🇩🇪",
    "usa": "🇺🇸",
    "cdn": "🇨🇦",
    "f": "🇫🇷",
    "s": "🇸🇪",
    "i": "🇮🇹",
    "nl": "🇳🇱",
    "b": "🇧🇪",
    "ch": "🇨🇭",
    "a": "🇦🇹",
    "gb": "🇬🇧",
    "j": "🇯🇵",
    "e": "🇪🇸",
    "cz": "🇨🇿",
    "dk": "🇩🇰",
    "n": "🇳🇴",
    "fin": "🇫🇮",
    "h": "🇭🇺",
    "sk": "🇸🇰",
    "ua": "🇺🇦",
    "lt": "🇱🇹",
    "lv": "🇱🇻",
    "slo": "🇸🇮",
    "hr": "🇭🇷",
    "ro": "🇷🇴",
    "bg": "🇧🇬",
    "p": "🇵🇹",
    "irl": "🇮🇪",
    "l": "🇱🇺",
    "gr": "🇬🇷",
    "est": "🇪🇪",
    "rus": "🇷🇺",
}


def country_flag(code: str | None) -> str:
    """Flag emoji for an otomoto country code, or ``""`` if unknown."""
    return _FLAGS.get((code or "").strip().lower(), "")


def _fold(s: str) -> str:
    """Lowercase + strip diacritics so patterns match 'Włochy'/'wloch' alike."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# Country detection from free text. Each entry: canonical label (matches
# otomoto's own Polish name so text- and param-derived chips merge), otomoto
# code (-> flag), a fast substring regex over diacritic-folded text, and a few
# distinctive words for a difflib fuzzy fallback that tolerates the typos and
# odd inflections the stems miss ("norwgia", "sprowdzony").
_COUNTRIES: list[tuple[str, str, re.Pattern[str], list[str]]] = [
    (lab, code, re.compile(rx), fuzzy)
    for lab, code, rx, fuzzy in [
        (
            "Stany Zjednoczone",
            "usa",
            r"\busa\b|u\.s\.a|stany zjedn|stanow zjedn|ameryk|import us\b",
            ["amerykanski", "zjednoczone"],
        ),
        ("Kanada", "cdn", r"kanad|canada", ["kanada", "kanadyjski"]),
        ("Niemcy", "d", r"niemc|niemiec|germany|deutsch", ["niemiecki", "deutschland"]),
        (
            "Szwajcaria",
            "ch",
            r"szwajcar|swiss|switzerland",
            ["szwajcaria", "szwajcarski"],
        ),
        ("Francja", "f", r"francj|francus|\bfrance\b", ["francuski", "francja"]),
        ("Włochy", "i", r"wloch|wlosk|italia|\bitaly\b", ["wlochy", "wloski"]),
        ("Szwecja", "s", r"szwec|szwedz|sweden", ["szwecja", "szwedzki"]),
        (
            "Holandia",
            "nl",
            r"holand|holender|niderland|netherlands",
            ["holandia", "holenderski"],
        ),
        ("Belgia", "b", r"belgi|belgium", ["belgia", "belgijski"]),
        ("Austria", "a", r"austri", ["austria", "austriacki"]),
        (
            "Wielka Brytania",
            "gb",
            r"brytan|brytyj|angli|angielsk|england|united kingdom",
            ["brytyjski", "anglii"],
        ),
        ("Japonia", "j", r"japon|\bjapan\b|\bjdm\b", ["japonia", "japonski"]),
        ("Norwegia", "n", r"norweg|norway", ["norwegia", "norweski"]),
        ("Dania", "dk", r"denmark|dunsk|\bdanii\b", ["denmark", "dunski"]),
        ("Hiszpania", "e", r"hiszpan|\bspain\b|espan", ["hiszpania", "hiszpanski"]),
        ("Czechy", "cz", r"czech|czesk", ["czechy", "czeski"]),
    ]
]

# Origin-status markers without a specific country. An "imported" marker must
# beat the Poland default; an explicit domestic claim beats "imported".
_IMPORT_RX = re.compile(r"sprowadz|importowan|\bimport\b|zagranic")
_DOMESTIC_RX = re.compile(r"krajow|salon polska|pierwszy wlascic|\bpolski\b")
_IMPORT_FUZZY = ["sprowadzony", "sprowadzona", "importowany"]
_FUZZY_CUTOFF = 0.86


def _fuzzy_hit(words: list[str], tokens: list[str]) -> bool:
    """True if any token is a difflib close-match to any of ``words``."""
    return any(
        difflib.get_close_matches(w, tokens, n=1, cutoff=_FUZZY_CUTOFF) for w in words
    )


def _match_country(folded: str, tokens: list[str]) -> tuple[str, str] | None:
    """Country from text: exact substring first, then a fuzzy-word fallback."""
    for lab, code, rx, _ in _COUNTRIES:
        if rx.search(folded):
            return lab, code
    for lab, code, _, fuzzy in _COUNTRIES:
        if _fuzzy_hit(fuzzy, tokens):
            return lab, code
    return None


def _resolve_country(text: str, listing: dict) -> tuple[str, str]:
    """``(label, code)`` for origin.

    Order: trust the structured ``country_origin`` param; else a country named
    in the free text (exact or fuzzy); else an explicit domestic claim
    ("krajowy", "salon Polska") -> Poland; else an "imported" marker
    ("sprowadzony", "import", "z zagranicy", incl. fuzzy) with no country -> a
    generic ``Sprowadzone`` bucket; else default to Poland.
    """
    label = (listing.get("country_label") or "").strip()
    if label:
        return label, (listing.get("country") or "")
    folded = _fold(text)
    tokens = [w for w in re.findall(r"[a-z]+", folded) if len(w) >= 5]
    country = _match_country(folded, tokens)
    if country:
        return country
    if _DOMESTIC_RX.search(folded):
        return "Polska", "pl"
    if _IMPORT_RX.search(folded) or _fuzzy_hit(_IMPORT_FUZZY, tokens):
        return "Sprowadzone", ""
    return "Polska", "pl"


def _kw(*words: str) -> re.Pattern[str]:
    """Word-boundary, case-insensitive alternation of keyword patterns."""
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)


def _first(text: str, pairs: list[tuple[str, re.Pattern[str]]]) -> str | None:
    """First canonical label whose pattern matches ``text`` (order = priority)."""
    for label, pat in pairs:
        if pat.search(text):
            return label
    return None


_LC_TRIM = [
    ("Inspiration Series", _kw("inspiration")),
    ("Bespoke", _kw("bespoke")),
    ("Prestige", _kw("prestige")),
]


def _lexus_lc(text: str, listing: dict) -> dict:
    """LC 500 (5.0 V8) vs 500h (3.5 V6 hybrid); body + trim from the marketing text."""
    cap = listing.get("engine_capacity") or 0
    fuel = (listing.get("fuel_type") or "").lower()
    is_h = (
        fuel == "hybrid" or bool(re.search(r"\b500h\b", text, re.I)) or 0 < cap < 4000
    )
    variant = "500h" if is_h else "500"

    body = (
        "Convertible"
        if re.search(r"cabrio|kabrio|convertible|roadster", text, re.I)
        else "Coupé"
    )

    superturismo = re.search(r"super\s?turismo", text, re.I)
    trim: str | None
    if superturismo and re.search(r"\bcarbon\b", text, re.I):
        trim = "Superturismo Carbon"
    elif superturismo:
        trim = "Superturismo"
    else:
        trim = _first(text, _LC_TRIM)
    return {"variant": variant, "body": body, "trim": trim}


_MX5_TRIM = [
    ("Homura", _kw("homura")),
    ("Sports-Line", _kw("sports-?line")),
    ("Exclusive-Line", _kw("exclusive-?line")),
    ("Prime-Line", _kw("prime-?line")),
    ("Skypassion", _kw("skypassion")),
    ("Skyfreedom", _kw("skyfreedom")),
    ("Skyenergy", _kw("skyenergy")),
    ("Anniversary", _kw("anniversary")),
    ("Kazari", _kw("kazari")),
    ("Kizuna", _kw("kizuna")),
]


def _mazda_mx5(text: str, _listing: dict) -> dict:
    """MX-5 RF (retractable hardtop) vs Soft-top (roadster) + trim line."""
    body = "RF" if re.search(r"\brf\b", text, re.I) else "Soft-top"
    return {"body": body, "trim": _first(text, _MX5_TRIM)}


_SUPRA_TRIM = [
    ("45th Anniversary", _kw("45th", "anniversary")),
    ("Legend", _kw("legend")),
    ("Executive", _kw("executive")),
    ("Pure", _kw("pure")),
]


def _toyota_supra(text: str, _listing: dict) -> dict:
    """Supra trim (every car is a GR, so GR alone is not a discriminator)."""
    return {"trim": _first(text, _SUPRA_TRIM)}


_GR86_TRIM = [
    ("Premium", _kw("premium")),
    ("Dynamic Force", _kw("dynamic")),
]


def _toyota_gr86(text: str, _listing: dict) -> dict:
    """GR86 trim (coupe-only 2.4 boxer; just split the named trims)."""
    return {"trim": _first(text, _GR86_TRIM)}


_XC90_TRIM = [
    ("Ultimate", _kw("ultimate")),
    ("Plus", _kw("plus")),
    ("Core", _kw("core")),
    ("Inscription", _kw("inscription")),
    ("R-Design", _kw("r-design", "r design")),
    ("Momentum", _kw("momentum")),
]


def _volvo_xc90(text: str, _listing: dict) -> dict:
    """XC90 B5 (mild-hybrid petrol) vs T8 (plug-in hybrid, marketed as 'Recharge')."""
    is_phev = bool(re.search(r"\bt8\b|recharge|plug-?in", text, re.I))
    variant = "T8" if is_phev else "B5"
    return {"variant": variant, "trim": _first(text, _XC90_TRIM)}


# model key -> classifier. Models not listed get only the shared origin facet.
_CLASSIFIERS = {
    "lexus-lc": _lexus_lc,
    "mazda-mx-5": _mazda_mx5,
    "toyota-supra": _toyota_supra,
    "toyota-gr86": _toyota_gr86,
    "volvo-xc90": _volvo_xc90,
}


def classify(model_key: str, listing: dict) -> dict:
    """Return facet values for one listing.

    Always includes ``country`` (display label) + ``flag``; model-specific
    classifiers add ``variant`` / ``body`` / ``trim`` where they apply. Values
    that can't be determined are ``None`` and simply produce no chip.
    """
    text = " ".join(
        str(listing.get(k) or "") for k in ("title", "version", "short_description")
    )
    fn = _CLASSIFIERS.get(model_key)
    facets: dict = fn(text, listing) if fn else {}
    label, code = _resolve_country(text, listing)
    facets["country"] = label
    facets["flag"] = country_flag(code)
    return facets


def _selfcheck() -> None:
    """Assert-based check of the classification heuristics."""
    # LC: V8 500 coupe, Superturismo Carbon from short_description only.
    f = classify(
        "lexus-lc",
        {
            "title": "Lexus LC",
            "version": None,
            "short_description": "Superturismo Carbon",
            "engine_capacity": 4969,
            "fuel_type": "petrol",
            "country": "usa",
            "country_label": "Stany Zjednoczone",
        },
    )
    assert f["variant"] == "500", f
    assert f["trim"] == "Superturismo Carbon", f
    assert f["body"] == "Coupé", f
    assert f["flag"] == "🇺🇸" and f["country"] == "Stany Zjednoczone", f

    # LC hybrid by engine + convertible by text.
    h = classify(
        "lexus-lc",
        {
            "title": "Lexus LC 500h Cabrio",
            "engine_capacity": 3456,
            "fuel_type": "hybrid",
        },
    )
    assert h["variant"] == "500h" and h["body"] == "Convertible", h

    # MX-5 RF vs soft-top.
    rf = classify("mazda-mx-5", {"title": "Mazda MX-5 RF SKYACTIV-G Homura"})
    soft = classify("mazda-mx-5", {"title": "Mazda MX-5 2.0 Sports-Line"})
    assert rf["body"] == "RF" and rf["trim"] == "Homura", rf
    assert soft["body"] == "Soft-top" and soft["trim"] == "Sports-Line", soft

    # Supra trim; no origin marker anywhere -> default Poland.
    s = classify("toyota-supra", {"title": "Toyota Supra 3.0 Turbo Executive"})
    assert s["trim"] == "Executive", s
    assert s["country"] == "Polska" and s["flag"] == "🇵🇱", s

    # Origin read from the description text when the param is absent.
    txt = classify(
        "mazda-mx-5",
        {"title": "Mazda MX-5", "short_description": "Miata Club | import USA"},
    )
    assert txt["country"] == "Stany Zjednoczone" and txt["flag"] == "🇺🇸", txt
    de = classify("lexus-lc", {"title": "Lexus LC 500 sprowadzony z Niemiec"})
    assert de["country"] == "Niemcy" and de["flag"] == "🇩🇪", de

    # "Imported" marker but no country named -> generic Sprowadzone bucket.
    imp = classify(
        "mazda-mx-5",
        {"title": "Mazda MX-5", "short_description": "auto sprowadzone, bezwypadkowe"},
    )
    assert imp["country"] == "Sprowadzone" and imp["flag"] == "", imp
    # Fuzzy import marker: typo'd "sprowdzony" still reads as imported.
    fz = classify(
        "toyota-supra", {"title": "Supra", "short_description": "swiezo sprowdzony"}
    )
    assert fz["country"] == "Sprowadzone", fz
    # Fuzzy country: misspelled "norwgia" -> Norwegia (and beats the import marker).
    nm = classify("lexus-lc", {"title": "Lexus LC sprowadzony z norwgia"})
    assert nm["country"] == "Norwegia", nm
    # Explicit domestic claim stays Poland.
    pl = classify(
        "lexus-lc", {"title": "Lexus LC", "short_description": "salon Polska, krajowy"}
    )
    assert pl["country"] == "Polska", pl

    # Structured param always wins over text.
    u = classify(
        "ford-focus", {"title": "Ford z USA", "country": "d", "country_label": "Niemcy"}
    )
    assert u == {"country": "Niemcy", "flag": "🇩🇪"}, u

    # XC90 T8 (Recharge PHEV) vs B5 (mild-hybrid petrol), trim from text.
    t8 = classify("volvo-xc90", {"title": "Volvo XC90 T8 Recharge Ultimate Bright"})
    b5 = classify("volvo-xc90", {"title": "Volvo XC90 B5 AWD Plus Dark"})
    assert t8["variant"] == "T8" and t8["trim"] == "Ultimate", t8
    assert b5["variant"] == "B5" and b5["trim"] == "Plus", b5

    print("facets self-check OK")


if __name__ == "__main__":
    _selfcheck()
