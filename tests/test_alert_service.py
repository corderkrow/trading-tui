"""AlertService lifecycle + evaluation tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.alert import CreateAlertRequest
from app.services.alerts.domain import (
    Alert,
    AlertEvent,
    AlertStatus,
    ConditionSpec,
    MatchMode,
    Operator,
    TriggerMode,
)
from app.services.alerts.errors import AlertExpired, AlertNotFound, InvalidAlertConfiguration
from app.services.alerts.repository import InMemoryAlertRepository
from app.services.alerts.service import AlertService
from app.services.notifications import NotificationService


def make_request(**overrides) -> CreateAlertRequest:
    base = {
        "symbol": "ETHUSDT",
        "conditions": [{"operator": "above", "value": 100.0}],
        "notification_channels": ["in_app"],
    }
    base.update(overrides)
    return CreateAlertRequest(**base)


class FakeChannel:
    name = "test_ch"

    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    async def notify(self, alert: Alert, event: AlertEvent) -> None:
        self.events.append(event)


def make_service(clock=None, channel=None) -> tuple[AlertService, FakeChannel | None]:
    notifications = NotificationService(channels={"test_ch": channel} if channel else None)
    kwargs = {"notifications": notifications}
    if clock is not None:
        kwargs["clock"] = clock
    return (
        AlertService(
            repository=InMemoryAlertRepository(),
            **kwargs,
        ),
        channel,
    )


async def test_create_stores_fields_and_default_message():
    service, _ = make_service()
    alert = await service.create(
        make_request(
            symbol="ETHUSD",
            conditions=[{"operator": "crossing", "value": 3794.94}],
        )
    )
    assert alert.symbol == "ETHUSD"
    assert alert.status is AlertStatus.ACTIVE
    assert alert.message == "ETHUSD Crossing 3,794.94"
    assert alert.conditions == [ConditionSpec(operator=Operator.CROSSING, value=3794.94)]


async def test_custom_message_is_kept():
    service, _ = make_service()
    alert = await service.create(make_request(message="Moon shot!"))
    assert alert.message == "Moon shot!"


async def test_unknown_channel_rejected():
    service, _ = make_service()
    with pytest.raises(InvalidAlertConfiguration):
        await service.create(make_request(notification_channels=["slack"]))


async def test_once_trigger_then_stays_triggered():
    clock = _clock()
    service, channel = make_service(clock=clock, channel=FakeChannel())
    alert = await service.create(
        make_request(notification_channels=["test_ch"])
    )
    events = await service.handle_price("ETHUSDT", 101.0, at=clock())
    assert len(events) == 1
    assert alert.status is AlertStatus.TRIGGERED
    assert alert.triggered_at is not None
    assert channel.events == events  # notification emitted

    second = await service.handle_price("ETHUSDT", 102.0, at=clock())
    assert second == []  # once-only: no second trigger
    assert len(channel.events) == 1


async def test_every_time_retriggers_each_tick():
    clock = _clock()
    service, _ = make_service(clock=clock)
    await service.create(make_request(trigger_mode="EVERY_TIME"))
    first = await service.handle_price("ETHUSDT", 101.0, at=clock())
    second = await service.handle_price("ETHUSDT", 102.0, at=clock())
    assert len(first) == 1
    assert len(second) == 1
    alert = (await service.list())[0]
    assert alert.status is AlertStatus.ACTIVE


async def test_crossing_detected_across_ticks():
    clock = _clock()
    service, _ = make_service(clock=clock)
    await service.create(
        make_request(conditions=[{"operator": "crossing", "value": 100.0}])
    )
    baseline = await service.handle_price("ETHUSDT", 99.0, at=clock())
    assert baseline == []
    fired = await service.handle_price("ETHUSDT", 101.0, at=clock())
    assert len(fired) == 1


async def test_expired_alert_not_evaluated():
    clock = _clock()
    service, channel = make_service(clock=clock, channel=FakeChannel())
    expires = clock() + timedelta(days=1)
    await service.create(
        make_request(
            expires_at=expires,
            notification_channels=["test_ch"],
        )
    )
    clock.advance(days=2)
    events = await service.handle_price("ETHUSDT", 101.0, at=clock())
    assert events == []
    assert channel.events == []
    alert = (await service.list())[0]
    assert alert.status is AlertStatus.EXPIRED


async def test_get_sweeps_expiration():
    clock = _clock()
    service, _ = make_service(clock=clock)
    await service.create(make_request(expires_at=clock() + timedelta(hours=1)))
    clock.advance(hours=2)
    alert = await service.get((await service.list())[0].id)
    assert alert.status is AlertStatus.EXPIRED


async def test_disabled_alert_not_evaluated():
    clock = _clock()
    service, _ = make_service(clock=clock)
    alert = await service.create(make_request())
    await service.disable(alert.id)
    events = await service.handle_price("ETHUSDT", 101.0, at=clock())
    assert events == []
    assert (await service.get(alert.id)).status is AlertStatus.DISABLED


async def test_all_and_any_combination():
    clock = _clock()
    service_all, _ = make_service(clock=clock)
    await service_all.create(
        make_request(
            conditions=[
                {"operator": "above", "value": 100.0},
                {"operator": "below", "value": 200.0},
            ],
            match_mode="ALL",
        )
    )
    assert len(await service_all.handle_price("ETHUSDT", 150.0, at=clock())) == 1
    assert await service_all.handle_price("ETHUSDT", 250.0, at=clock()) == []

    service_any, _ = make_service(clock=clock)
    await service_any.create(
        make_request(
            conditions=[
                {"operator": "above", "value": 100.0},
                {"operator": "below", "value": 200.0},
            ],
            match_mode="ANY",
        )
    )
    assert len(await service_any.handle_price("ETHUSDT", 250.0, at=clock())) == 1


async def test_enable_disable_lifecycle():
    clock = _clock()
    service, _ = make_service(clock=clock)
    alert = await service.create(make_request())
    await service.disable(alert.id)
    assert (await service.get(alert.id)).status is AlertStatus.DISABLED
    await service.enable(alert.id)
    assert (await service.get(alert.id)).status is AlertStatus.ACTIVE


async def test_enable_triggered_alert_rejected():
    clock = _clock()
    service, _ = make_service(clock=clock)
    alert = await service.create(make_request())
    await service.handle_price("ETHUSDT", 101.0, at=clock())
    with pytest.raises(InvalidAlertConfiguration):
        await service.enable(alert.id)


async def test_enable_expired_alert_rejected():
    clock = _clock()
    service, _ = make_service(clock=clock)
    alert = await service.create(make_request(expires_at=clock() + timedelta(minutes=5)))
    clock.advance(minutes=10)
    with pytest.raises(AlertExpired):
        await service.enable(alert.id)


async def test_delete_removes_alert():
    service, _ = make_service()
    alert = await service.create(make_request())
    await service.delete(alert.id)
    with pytest.raises(AlertNotFound):
        await service.get(alert.id)


async def test_disable_expired_rejected():
    clock = _clock()
    service, _ = make_service(clock=clock)
    alert = await service.create(make_request(expires_at=clock() + timedelta(minutes=5)))
    clock.advance(minutes=10)
    with pytest.raises(AlertExpired):
        await service.disable(alert.id)


def _clock():
    class Clock:
        def __init__(self) -> None:
            self.now = datetime(2090, 1, 1, tzinfo=timezone.utc)

        def __call__(self) -> datetime:
            return self.now

        def advance(self, **kwargs) -> None:
            self.now += timedelta(**kwargs)

    return Clock()