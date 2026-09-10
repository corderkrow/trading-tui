"""InMemoryAlertRepository behavior tests."""

import pytest

from app.services.alerts.domain import Alert
from app.services.alerts.errors import AlertNotFound
from app.services.alerts.repository import InMemoryAlertRepository


async def test_create_get_list_roundtrip():
    repo = InMemoryAlertRepository()
    alert = Alert(symbol="BTCUSDT")
    await repo.create(alert)
    assert await repo.get(alert.id) is alert
    assert await repo.list() == [alert]


async def test_update_persists_changes():
    repo = InMemoryAlertRepository()
    alert = Alert(symbol="BTCUSDT")
    await repo.create(alert)
    alert.symbol = "ETHUSDT"
    await repo.update(alert)
    assert (await repo.get(alert.id)).symbol == "ETHUSDT"


async def test_delete_removes_alert():
    repo = InMemoryAlertRepository()
    alert = Alert(symbol="BTCUSDT")
    await repo.create(alert)
    await repo.delete(alert.id)
    with pytest.raises(AlertNotFound):
        await repo.get(alert.id)


async def test_missing_alert_raises_not_found():
    repo = InMemoryAlertRepository()
    with pytest.raises(AlertNotFound):
        await repo.get("nope")
    with pytest.raises(AlertNotFound):
        await repo.update(Alert(id="nope", symbol="X"))
    with pytest.raises(AlertNotFound):
        await repo.delete("nope")