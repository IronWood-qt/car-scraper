"""Pushover push notifications for car alerts.

Reads credentials from ``PUSHOVER_TOKEN`` (application token) and
``PUSHOVER_USER`` (user/group key) when not passed explicitly. Both must be
set for anything to be sent; otherwise this is a silent no-op so local runs
and forks without the secrets configured don't fail the pipeline.
"""

import os

import httpx

from src.car_scraper.utils.logger import logger

_API_URL = "https://api.pushover.net/1/messages.json"
_MAX_TITLE_LEN = 250
_MAX_MESSAGE_LEN = 1024  # Pushover's hard limit
_MAX_URL_LEN = 512
_MAX_URL_TITLE_LEN = 100


def send_pushover(
    title: str,
    message: str,
    token: str | None = None,
    user: str | None = None,
    url: str | None = None,
    url_title: str | None = None,
) -> bool:
    """Send a Pushover notification. Returns ``True`` if it was accepted.

    Falls back to the ``PUSHOVER_TOKEN`` / ``PUSHOVER_USER`` env vars when
    ``token`` / ``user`` aren't passed. No-ops (returns ``False``, logs at
    debug level) when neither is available.
    """
    token = token or os.environ.get("PUSHOVER_TOKEN")
    user = user or os.environ.get("PUSHOVER_USER")
    if not token or not user:
        logger.debug(
            "Pushover not configured (PUSHOVER_TOKEN/PUSHOVER_USER unset) - skipping"
        )
        return False

    payload = {
        "token": token,
        "user": user,
        "title": title[:_MAX_TITLE_LEN],
        "message": message[:_MAX_MESSAGE_LEN],
    }
    if url:
        payload["url"] = url[:_MAX_URL_LEN]
        if url_title:
            payload["url_title"] = url_title[:_MAX_URL_TITLE_LEN]

    try:
        resp = httpx.post(_API_URL, data=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Pushover notification sent")
        return True
    except Exception as exc:  # noqa: BLE001 - don't fail the pipeline on a notify error
        logger.error(f"Pushover notification failed: {exc}")
        return False
