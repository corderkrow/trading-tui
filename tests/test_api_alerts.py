"""REST API tests for /alerts endpoints."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.main import create_app
from app.services.alerts.repository import InMemoryAlertRepository
from app.services.alerts.service import AlertService
from app.services.notifications import NotificationService
from tests.conftest import FakeClock

BASE = "http://test"


def make_client(clock=None):
    kwargs = {
        "repository": InMemoryAlertRepository(),
        "notifications": NotificationService(),
    }
    if clock is not None:
        kwargs["clock"] = clock
    service = AlertService(**kwargs)
    app = create_app(alert_service=service)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


def payload(**overrides) -> dict:
    body = {
        "symbol": "ETHUSDT",
        "conditions": [{"operator": "above", "value": 100.0}],
        "notification_channels": ["in_app"],
    }
    body.update(overrides)
    return body


async def test_create_and_get_alert():
    async with make_client() as client:
        resp = await client.post("/alerts", json=payload(symbol=" ethusdt "))
        assert resp.status_code == 201
        body = resp.json()
        assert body["symbol"] == "ETHUSDT"
        assert body["status"] == "ACTIVE"
        alert_id = body["id"]

        got = await client.get(f"/alerts/{alert_id}")
        assert got.status_code == 200
        assert got.json()["message"] == "ETHUSDT Above 100"


async def test_list_alerts():
    async with make_client() as client:
        await client.post("/alerts", json=payload())
        await client.post("/alerts", json=payload(symbol="BTCUSDT"))
        resp = await client.get("/alerts")
        assert resp.status_code == 200
        assert {a["symbol"] for a in resp.json()} == {"ETHUSDT", "BTCUSDT"}


async def test_delete_alert():
    async with make_client() as client:
        created = await client.post("/alerts", json=payload())
        alert_id = created.json()["id"]
        resp = await client.delete(f"/alerts/{alert_id}")
        assert resp.status_code == 204
        assert (await client.get(f"/alerts/{alert_id}")).status_code == 404


async def test_get_missing_alert_returns_404():
    async with make_client() as client:
        resp = await client.get("/alerts/does-not-exist")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


async def test_disable_and_enable():
    async with make_client() as client:
        alert_id = (await client.post("/alerts", json=payload())).json()["id"]
        disabled = await client.post(f"/alerts/{alert_id}/disable")
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "DISABLED"
        enabled = await client.post(f"/alerts/{alert_id}/enable")
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "ACTIVE"


async def test_validation_errors():
    async with make_client() as client:
        cases = [
            payload(conditions=[]),                      # at least one condition
            payload(conditions=[{"operator": "above", "value": 0}]),  # value must be > 0
            payload(conditions=[{"operator": "above", "value": -5}]),
            payload(symbol="   "),                        # empty symbol
            payload(expires_at="2026-10-06T15:13:00"),    # naive datetime
            payload(expires_at="2020-01-01T00:00:00Z"),   # past expiration
            payload(notification_channels=[]),            # at least one channel
            payload(notification_channels=["slack"]),     # unknown channel
            payload(conditions=[{"operator": "sideways", "value": 1}]),  # bad operator
        ]
        for body in cases:
            resp = await client.post("/alerts", json=body)
            assert resp.status_code == 422, f"expected 422 for {body}"
            assert "detail" in resp.json()


async def test_evaluate_triggers_once_only():
    async with make_client() as client:
        await client.post("/alerts", json=payload())
        first = await client.post("/alerts/evaluate", json={"symbol": "ETHUSDT", "price": 101.0})
        assert first.status_code == 200
        assert len(first.json()) == 1
        assert first.json()[0]["message"] == "ETHUSDT Above 100"

        second = await client.post("/alerts/evaluate", json={"symbol": "ETHUSDT", "price": 150.0})
        assert second.json() == []


async def test_expired_alert_flow():
    clock = FakeClock()
    async with make_client(clock=clock) as client:
        expires = (clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        alert_id = (await client.post("/alerts", json=payload(expires_at=expires))).json()["id"]

        clock.advance(days=2)
        got = await client.get(f"/alerts/{alert_id}")
        assert got.json()["status"] == "EXPIRED"

        enable = await client.post(f"/alerts/{alert_id}/enable")
        assert enable.status_code == 409

        events = await client.post("/alerts/evaluate", json={"symbol": "ETHUSDT", "price": 999.0})
        assert events.json() == []


async def test_evaluate_validates_price():
    async with make_client() as client:
        resp = await client.post("/alerts/evaluate", json={"symbol": "ETHUSDT", "price": -1})
        assert resp.status_code == 422