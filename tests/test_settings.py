"""Tests for user settings model + persistence."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from tui_client.settings import UserSettings, load_settings, save_settings


def test_defaults() -> None:
    s = UserSettings()
    assert s.watchlist.mode == "single"
    assert s.watchlist.active_symbols()
    assert s.notifications.price_change_sources == "watchlist"
    assert s.notifications.price_alert_delivery == "in_app"
    assert s.notifications.enabled_thresholds() == [2.0, 5.0, 20.0]


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = UserSettings()
    s.watchlist.mode = "multiple"
    s.watchlist.watchlists = {"crypto": ["BTC-USD"], "stocks": ["AAPL"]}
    s.watchlist.active = "stocks"
    s.notifications.custom_threshold = 7.5
    s.notifications.price_alert_delivery = "push_email"
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded == s


def test_load_missing_returns_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "nope.json") == UserSettings()


def test_load_corrupt_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    assert load_settings(path) == UserSettings()


def test_active_falls_back_when_missing(tmp_path: Path) -> None:
    s = UserSettings()
    s.watchlist.active = "does-not-exist"
    assert s.watchlist.active in s.watchlist.watchlists


def test_symbols_uppercased() -> None:
    s = UserSettings()
    s.watchlist.watchlists = {"default": ["btc-usd", "aapl"]}
    assert s.watchlist.active_symbols() == ["BTC-USD", "AAPL"]


def test_empty_watchlists_rejected() -> None:
    with pytest.raises(ValidationError):
        UserSettings.model_validate({"watchlist": {"watchlists": {}}})


def test_custom_threshold_bounds() -> None:
    s = UserSettings()
    s.notifications.custom_threshold = 100.0
    assert s.notifications.custom_threshold == 100.0
    with pytest.raises(ValidationError):
        s.notifications.custom_threshold = 0
    with pytest.raises(ValidationError):
        s.notifications.custom_threshold = 150


def test_enabled_thresholds_dedupes_and_sorts() -> None:
    n = UserSettings().notifications
    n.price_change_thresholds = [5.0, 2.0, 2.0]
    n.custom_threshold = 3.5
    assert n.enabled_thresholds() == [2.0, 3.5, 5.0]
