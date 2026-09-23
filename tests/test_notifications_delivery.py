"""Tests: delivery-preference filtering, user_prefs reader, price-change monitor."""

import json
from pathlib import Path

import pytest

from app.services.alerts.domain import Alert, AlertEvent
from app.services.notifications import InAppChannel, NotificationService, NoopChannel
from app.services.user_prefs import allowed_channels
from tui_client.api import QuoteView
from tui_client.monitor import PriceChangeMonitor, event_message
from tui_client.settings import UserSettings


# ── user_prefs ───────────────────────────────────────────────

def _write_prefs(path: Path, delivery: str) -> Path:
    path.write_text(json.dumps({"notifications": {"price_alert_delivery": delivery}}))
    return path


def test_allowed_channels_map(tmp_path: Path) -> None:
    assert allowed_channels(_write_prefs(tmp_path / "s.json", "none")) == set()
    assert allowed_channels(_write_prefs(tmp_path / "s.json", "push")) == {"push"}
    assert allowed_channels(_write_prefs(tmp_path / "s.json", "in_app")) == {"in_app"}
    assert allowed_channels(_write_prefs(tmp_path / "s.json", "push_email")) == {
        "push",
        "email",
    }


def test_allowed_channels_missing_file_is_none(tmp_path: Path) -> None:
    assert allowed_channels(tmp_path / "nope.json") is None


def test_allowed_channels_corrupt_is_none(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{oops")
    assert allowed_channels(path) is None


def test_allowed_channels_unknown_delivery_is_none(tmp_path: Path) -> None:
    assert allowed_channels(_write_prefs(tmp_path / "s.json", "telepathy")) is None


def test_allowed_channels_cached_until_mtime_changes(tmp_path: Path, monkeypatch) -> None:
    path = _write_prefs(tmp_path / "s.json", "push")
    assert allowed_channels(path) == {"push"}

    reads = {"n": 0}
    original = Path.read_text

    def counting(self, *args, **kwargs):
        reads["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    assert allowed_channels(path) == {"push"}
    assert reads["n"] == 0  # served from cache, no disk read on dispatch

    _write_prefs(path, "none")
    assert allowed_channels(path) == set()  # mtime changed -> re-read


# ── delivery filter on NotificationService ───────────────────

def _alert(channels: list[str]) -> Alert:
    return Alert(symbol="BTC-USD", notification_channels=channels)


def _event() -> AlertEvent:
    return AlertEvent(alert_id="a1", symbol="BTC-USD", message="m", conditions=())


async def test_dispatch_unfiltered_sends_all() -> None:
    in_app = InAppChannel()
    ns = NotificationService(channels={"in_app": in_app, "push": NoopChannel("push")})
    ns.dispatch.__self__  # just exists
    await ns.dispatch(_alert(["in_app", "push"]), _event())
    assert len(in_app.events) == 1


async def test_delivery_filter_ignores_blocked_channels() -> None:
    in_app = InAppChannel()
    ns = NotificationService(
        channels={"in_app": in_app, "push": NoopChannel("push")},
        delivery_filter=lambda: {"push", "email"},  # user chose push only
    )
    await ns.dispatch(_alert(["in_app", "push"]), _event())
    assert in_app.events == []


async def test_delivery_filter_none_means_no_pref() -> None:
    in_app = InAppChannel()
    ns = NotificationService(
        channels={"in_app": in_app},
        delivery_filter=lambda: None,
    )
    await ns.dispatch(_alert(["in_app"]), _event())
    assert len(in_app.events) == 1


async def test_delivery_filter_reread_per_dispatch() -> None:
    state = {"allowed": {"in_app"}}
    in_app = InAppChannel()
    ns = NotificationService(
        channels={"in_app": in_app},
        delivery_filter=lambda: state["allowed"],
    )
    await ns.dispatch(_alert(["in_app"]), _event())
    state["allowed"] = set()  # user flipped to "none"
    await ns.dispatch(_alert(["in_app"]), _event())
    assert len(in_app.events) == 1


# ── price-change monitor ─────────────────────────────────────

class FakeApi:
    def __init__(self, quotes: list[QuoteView]) -> None:
        self.quotes = quotes
        self.calls: list[list[str]] = []

    async def get_quotes(self, symbols: list[str]) -> list[QuoteView]:
        self.calls.append(symbols)
        return [q for q in self.quotes if q.symbol in symbols]


def _settings(**kwargs) -> UserSettings:
    s = UserSettings()
    s.notifications.price_change_sources = kwargs.get("sources", "watchlist")
    s.notifications.price_change_thresholds = kwargs.get("thresholds", [5.0])
    s.watchlist.watchlists = {"default": ["BTC-USD", "AAPL"]}
    return s


def _quote(symbol: str, change: float | None) -> QuoteView:
    return QuoteView(symbol=symbol, price=100.0, change_24h=change)


async def test_monitor_fires_on_threshold_entry() -> None:
    events: list[tuple[str, float, float]] = []
    api = FakeApi([_quote("BTC-USD", 6.0), _quote("AAPL", 1.0)])
    monitor = PriceChangeMonitor(
        api, lambda: _settings(), on_event=lambda s, c, t: _collect(events, s, c, t)
    )
    fired = await monitor.poll_once()
    assert ("BTC-USD", 6.0, 5.0) in fired
    assert all(e[0] != "AAPL" for e in fired)  # 1% < 5%
    assert len(fired) == 1


async def _collect(events: list, symbol: str, change: float, threshold: float) -> None:
    events.append((symbol, change, threshold))


async def test_monitor_rearms_after_leaving_zone() -> None:
    events: list[tuple[str, float, float]] = []
    quotes = [[_quote("BTC-USD", c)] for c in [7.0, 3.0, 7.0]]
    idx = {"i": 0}

    class Api:
        async def get_quotes(self, symbols: list[str]) -> list[QuoteView]:
            q = quotes[idx["i"]]
            idx["i"] += 1
            return q

    monitor = PriceChangeMonitor(
        Api(), lambda: _settings(), on_event=lambda s, c, t: _collect(events, s, c, t)
    )
    await monitor.poll_once()   # enters zone → fire
    await monitor.poll_once()   # below threshold → no fire
    await monitor.poll_once()   # re-enters → fire again
    assert len(events) == 2


async def test_monitor_sources_portfolio_is_empty() -> None:
    api = FakeApi([_quote("BTC-USD", 50.0)])
    monitor = PriceChangeMonitor(
        api, lambda: _settings(sources="portfolio"), on_event=_noop
    )
    assert monitor.source_symbols() == []


async def test_monitor_sources_both_uses_watchlist() -> None:
    api = FakeApi([_quote("BTC-USD", 50.0)])
    monitor = PriceChangeMonitor(api, lambda: _settings(sources="both"), on_event=_noop)
    assert monitor.source_symbols() == ["BTC-USD", "AAPL"]


async def _noop(symbol: str, change: float, threshold: float) -> None:
    pass


def test_event_message() -> None:
    assert event_message("BTC", 6.0, 5.0) == "BTC moved +6.00% (≥ 5% threshold)"


async def test_monitor_uses_enabled_thresholds() -> None:
    s = _settings(thresholds=[2.0])
    s.notifications.custom_threshold = 10.0
    api = FakeApi([_quote("BTC-USD", 6.0), _quote("AAPL", -11.0)])
    events: list[tuple[str, float, float]] = []

    async def on_event(symbol, change, threshold) -> None:
        events.append((symbol, change, threshold))

    monitor = PriceChangeMonitor(api, lambda: s, on_event=on_event)
    fired = await monitor.poll_once()
    assert ("BTC-USD", 6.0, 2.0) in fired
    assert ("AAPL", -11.0, 10.0) in fired
    assert ("BTC-USD", 6.0, 10.0) not in fired
