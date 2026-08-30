"""Unit tests for the Pushover notifier (no network)."""

import httpx
import pytest

from src.car_scraper.notifiers.pushover import send_pushover
from src.car_scraper.reporting import format_alert_pushover


def test_noop_without_credentials(monkeypatch):
    """No token/user (arg or env) -> no-op, no network call."""
    monkeypatch.delenv("PUSHOVER_TOKEN", raising=False)
    monkeypatch.delenv("PUSHOVER_USER", raising=False)
    assert send_pushover("title", "message") is False


def test_sends_with_explicit_credentials(monkeypatch):
    sent = {}

    def fake_post(url, data=None, timeout=None):
        sent["url"] = url
        sent["data"] = data
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    ok = send_pushover(
        "New car!", "Volvo XC90 dropped in price", token="tok", user="usr"
    )
    assert ok is True
    assert sent["data"]["token"] == "tok"
    assert sent["data"]["user"] == "usr"
    assert sent["data"]["title"] == "New car!"


def test_env_credentials_used_when_args_omitted(monkeypatch):
    sent = {}
    monkeypatch.setenv("PUSHOVER_TOKEN", "env-tok")
    monkeypatch.setenv("PUSHOVER_USER", "env-usr")

    def fake_post(url, data=None, timeout=None):
        sent["data"] = data
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert send_pushover("t", "m") is True
    assert sent["data"]["token"] == "env-tok"
    assert sent["data"]["user"] == "env-usr"


def test_http_error_is_caught_not_raised(monkeypatch):
    def fake_post(url, data=None, timeout=None):
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert send_pushover("t", "m", token="tok", user="usr") is False


def test_message_and_title_are_capped(monkeypatch):
    sent = {}

    def fake_post(url, data=None, timeout=None):
        sent["data"] = data
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    send_pushover("x" * 500, "y" * 2000, token="tok", user="usr")
    assert len(sent["data"]["title"]) == 250
    assert len(sent["data"]["message"]) == 1024


def test_url_included_when_given(monkeypatch):
    sent = {}

    def fake_post(url, data=None, timeout=None):
        sent["data"] = data
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    send_pushover(
        "t", "m", token="tok", user="usr", url="https://example.com", url_title="Open"
    )
    assert sent["data"]["url"] == "https://example.com"
    assert sent["data"]["url_title"] == "Open"


@pytest.mark.parametrize("new,drops", [([], []), ([{"current_price": 1}], [])])
def test_format_alert_pushover_within_limits(new, drops):
    title, message = format_alert_pushover(new, drops, "2026-08-30")
    assert len(title) <= 250
    assert len(message) <= 1024
