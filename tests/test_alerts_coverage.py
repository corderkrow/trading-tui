"""Coverage tests for the alert-monitoring loop.

Covers the fixes that make stored alerts actually fire end-to-end:

- `handle_price` only evaluates alerts for the ticked symbol.
- Channel failures during dispatch don't abort other channels.
- The in-app channel keeps a bounded, newest-first event log.
- `GET /alerts/events` exposes that log over REST.
- `BackgroundAlertEvaluator` polls active-alert symbols and feeds ticks.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.main import create_app
from app.models.alert import CreateAlertRequest
from app.models.ticker import Ticker
from app.services.adapters.base import MarketDataAdapter
from app.services.alerts.evaluator import BackgroundAlertEvaluator
from app.services.alerts.repository import InMemoryAlertRepository
from app.services.alerts.service import AlertService
from app.services.notifications import InAppChannel, NotificationService
from tests.conftest import FakeClock

BASE = "http://test"


def make_request(**overrides) -> CreateAlertRequest:
    base = {
        "symbol": "ETHUSDT",
        "conditions": [{"operator": "above", "value": 100.0}],
        "notification_channels": ["in_app"],
    }
    base.update(overrides)
    return CreateAlertRequest(**base)


# ── handle_price symbol filter ────────────────────────────────────────────


async def test_handle_price_ignores_other_symbols():
    service = AlertService(
        repository=InMemoryAlertRepository(),
        notifications=NotificationService(),
    )
    await service.create(make_request())  # ETHUSDT above 100

    # Tick a different symbol: nothing fires, alert untouched.
    assert await service.handle_price("BTCUSDT", 999.0) == []
    alerts = await service.list()
    assert alerts[0].status.value == "ACTIVE"
    assert alerts[0].last_evaluated_at is None

    # Tick the alert's own symbol: fires.
    events = await service.handle_price("ETHUSDT", 101.0)
    assert len(events) == 1
    assert events[0].symbol == "ETHUSDT"


# ── dispatch isolation ────────────────────────────────────────────────────


class BrokenChannel:
    name = "broken"

    async def notify(self, alert, event) -> None:
        raise RuntimeError("boom")


class RecordingChannel:
    name = "recorder"

    def __init__(self) -> None:
        self.events = []

    async def notify(self, alert, event) -> None:
        self.events.append(event)


async def test_dispatch_channel_failure_does_not_block_others(capfd):
    recorder = RecordingChannel()
    notifications = NotificationService(
        channels={"in_app": InAppChannel(), "broken": BrokenChannel(), "rec": recorder}
    )
    service = AlertService(
        repository=InMemoryAlertRepository(), notifications=notifications
    )
    await service.create(make_request(notification_channels=["rec", "broken"]))
    events = await service.handle_price("ETHUSDT", 101.0)
    assert len(events) == 1
    assert len(recorder.events) == 1  # healthy channel still delivered
    captured = capfd.readouterr()
    assert "broken" in captured.err


# ── in-app event log ──────────────────────────────────────────────────────


async def test_in_app_channel_ring_buffer_and_recent_order():
    from app.services.alerts.domain import Alert, AlertEvent

    channel = InAppChannel(maxlen=3)
    now = datetime.now(timezone.utc)
    for i in range(5):
        await channel.notify(
            Alert(symbol="X"),
            AlertEvent(
                alert_id=f"a{i}",
                symbol="X",
                message=str(i),
                conditions=(),
                triggered_at=now,
            ),
        )
    recent = channel.recent(10)
    assert [e.message for e in recent] == ["4", "3", "2"]  # newest first, capped
    assert len(channel.events) == 3


# ── /alerts/events endpoint ───────────────────────────────────────────────


def make_client():
    service = AlertService(
        repository=InMemoryAlertRepository(),
        notifications=NotificationService(),
    )
    app = create_app(alert_service=service, enable_evaluator=False)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


async def test_events_endpoint_returns_fired_events():
    async with make_client() as client:
        resp = await client.post("/alerts", json=make_request().model_dump(mode="json"))
        assert resp.status_code == 201
        empty = await client.get("/alerts/events")
        assert empty.status_code == 200
        assert empty.json() == []
        await client.post("/alerts/evaluate", json={"symbol": "ETHUSDT", "price": 150.0})
        feed = await client.get("/alerts/events")
        events = feed.json()
        assert len(events) == 1
        assert events[0]["symbol"] == "ETHUSDT"
        assert events[0]["alert_id"]


# ── background evaluator ──────────────────────────────────────────────────


class FakeAdapter(MarketDataAdapter):
    @property
    def name(self) -> str:
        return "fake"

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = prices
        self.requests: list[list[str]] = []

    async def fetch_candles(self, *args, **kwargs):
        raise NotImplementedError

    async def fetch_tickers(self, symbols):
        self.requests.append(list(symbols))
        return [
            Ticker(symbol=s, price=p)
            for s, p in self._prices.items()
            if s in symbols
        ]


async def test_evaluator_polls_only_active_symbols_and_fires():
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service = AlertService(
        repository=InMemoryAlertRepository(), notifications=NotificationService(), clock=clock
    )
    await service.create(make_request())  # ETHUSDT above 100
    await service.create(make_request(symbol="SOLUSDT", conditions=[{"operator": "above", "value": 10.0}]))
    await service.disable((await service.list())[1].id)  # SOLUSDT disabled
    adapter = FakeAdapter({"ETHUSDT": 120.0, "SOLUSDT": 50.0})
    evaluator = BackgroundAlertEvaluator(service, adapter, poll_seconds=1)

    fired = await evaluator.poll_once()
    # ETHUSDT evaluates and fires; the disabled SOLUSDT alert is fetched but
    # its handle_price pass matches nothing (status != ACTIVE).
    assert fired == [("ETHUSDT", 120.0, 1)]
    assert adapter.requests == [["ETHUSDT", "SOLUSDT"]]
    alerts = await service.list()
    eth = next(a for a in alerts if a.symbol == "ETHUSDT")
    assert eth.status.value == "TRIGGERED"


async def test_evaluator_sweeps_dropped_symbols():
    clock = FakeClock(datetime(2090, 1, 1, tzinfo=timezone.utc))
    service = AlertService(
        repository=InMemoryAlertRepository(), notifications=NotificationService(), clock=clock
    )
    await service.create(
        # Expires 30 min after clock start; create requires future expiry.
        make_request(expires_at=datetime(2090, 1, 1, 0, 30, tzinfo=timezone.utc))
    )
    # Adapter returns nothing for the symbol (delisted/halted).
    adapter = FakeAdapter({})
    evaluator = BackgroundAlertEvaluator(service, adapter, poll_seconds=1)
    clock.advance(hours=1)
    fired = await evaluator.poll_once()
    assert ("ETHUSDT", 0.0, 0) in fired
    alerts = await service.list()
    assert alerts[0].status.value == "EXPIRED"
