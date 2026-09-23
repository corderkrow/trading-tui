"""Repository abstraction + in-memory implementation for alerts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.services.alerts.domain import Alert
from app.services.alerts.errors import AlertNotFound


class AlertRepository(Protocol):
    async def create(self, alert: Alert) -> Alert: ...
    async def get(self, alert_id: str) -> Alert: ...
    async def list(self) -> list[Alert]: ...
    async def update(self, alert: Alert) -> Alert: ...
    async def update_many(self, alerts: Sequence[Alert]) -> None: ...
    async def delete(self, alert_id: str) -> None: ...


class InMemoryAlertRepository:
    """MVP storage. Swap for Sqlite/Postgres repository later."""

    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}

    async def create(self, alert: Alert) -> Alert:
        self._alerts[alert.id] = alert
        return alert

    async def get(self, alert_id: str) -> Alert:
        try:
            return self._alerts[alert_id]
        except KeyError:
            raise AlertNotFound(alert_id) from None

    async def list(self) -> list[Alert]:
        return list(self._alerts.values())

    async def update(self, alert: Alert) -> Alert:
        if alert.id not in self._alerts:
            raise AlertNotFound(alert.id)
        self._alerts[alert.id] = alert
        return alert

    async def update_many(self, alerts: Sequence[Alert]) -> None:
        for alert in alerts:
            if alert.id not in self._alerts:
                raise AlertNotFound(alert.id)
        for alert in alerts:
            self._alerts[alert.id] = alert

    async def delete(self, alert_id: str) -> None:
        if alert_id not in self._alerts:
            raise AlertNotFound(alert_id)
        del self._alerts[alert_id]