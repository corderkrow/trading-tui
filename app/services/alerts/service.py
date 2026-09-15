"""AlertService — alert CRUD, lifecycle, and evaluation.

Receives market price updates (Observer-style entry point `handle_price`)
and evaluates active alerts against them. Conditions are evaluated via
strategies; matches are fanned out through the NotificationService.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from app.services.alerts.conditions import build_condition
from app.services.alerts.domain import (
    Alert,
    AlertEvent,
    AlertStatus,
    ConditionSpec,
    MarketContext,
    MatchMode,
    TriggerMode,
    now_utc,
)
from app.services.alerts.errors import AlertExpired, InvalidAlertConfiguration
from app.services.alerts.repository import AlertRepository
from app.services.notifications import NotificationService

Clock = Callable[[], datetime]

if TYPE_CHECKING:
    from app.models.alert import CreateAlertRequest


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        notifications: NotificationService | None = None,
        clock: Clock = now_utc,
    ) -> None:
        self.repository = repository
        self.notifications = notifications or NotificationService()
        self._clock = clock
        # Previous tick state per symbol — needed for crossing/variation/turn conditions.
        self._previous_prices: dict[str, float] = {}
        self._previous_changes: dict[str, float] = {}

    async def create(self, request: CreateAlertRequest) -> Alert:
        now = self._clock()
        unknown = set(request.notification_channels) - self.notifications.channel_names
        if unknown:
            raise InvalidAlertConfiguration(
                f"Unknown notification channel(s): {', '.join(sorted(unknown))}"
            )
        alert = Alert(
            symbol=request.symbol,
            conditions=[c.to_spec() for c in request.conditions],
            match_mode=request.match_mode,
            trigger_mode=request.trigger_mode,
            expires_at=request.expires_at,
            message=request.message or self._default_message(request),
            notification_channels=list(request.notification_channels),
            status=AlertStatus.ACTIVE,
            created_at=now,
        )
        return await self.repository.create(alert)

    async def get(self, alert_id: str) -> Alert:
        alert = await self.repository.get(alert_id)
        await self._expire_if_needed(alert)
        return alert

    async def list(self) -> list[Alert]:
        alerts = await self.repository.list()
        for alert in alerts:
            await self._expire_if_needed(alert)
        return alerts

    async def delete(self, alert_id: str) -> None:
        await self.repository.delete(alert_id)

    async def enable(self, alert_id: str) -> Alert:
        alert = await self.repository.get(alert_id)
        await self._raise_if_expired(alert)
        if alert.status == AlertStatus.TRIGGERED:
            raise InvalidAlertConfiguration("Triggered alerts cannot be re-enabled")
        alert.status = AlertStatus.ACTIVE
        return await self.repository.update(alert)

    async def disable(self, alert_id: str) -> Alert:
        alert = await self.repository.get(alert_id)
        await self._raise_if_expired(alert)
        alert.status = AlertStatus.DISABLED
        return await self.repository.update(alert)

    async def handle_price(self, symbol: str, price: float, at: datetime | None = None) -> list[AlertEvent]:
        """Observer entry point: react to a market price update."""
        now = at or self._clock()
        triggered: list[AlertEvent] = []
        for alert in await self.repository.list():
            if alert.status is not AlertStatus.ACTIVE:
                continue
            if alert.expires_at is not None and alert.expires_at <= now:
                alert.status = AlertStatus.EXPIRED
                await self.repository.update(alert)
                continue
            if await self._matches(alert, symbol, price, now):
                event = AlertEvent(
                    alert_id=alert.id,
                    symbol=symbol,
                    message=alert.message,
                    conditions=tuple(alert.conditions),
                    triggered_at=now,
                )
                triggered.append(event)
                if alert.trigger_mode == TriggerMode.ONCE:
                    alert.status = AlertStatus.TRIGGERED
                    alert.triggered_at = now
            alert.last_evaluated_at = now
            await self.repository.update(alert)
        for event in triggered:
            alert = await self.repository.get(event.alert_id)
            await self.notifications.dispatch(alert, event)
        return triggered

    async def _matches(self, alert: Alert, symbol: str, price: float, now: datetime) -> bool:
        previous_price = self._previous_prices.get(symbol)
        change = self._percent_change(previous_price, price)
        previous_change = self._previous_changes.get(symbol)
        results: list[bool] = []
        for spec in alert.conditions:
            context = MarketContext(
                symbol=symbol,
                price=price,
                previous_price=previous_price,
                change=change,
                previous_change=previous_change,
                at=now,
            )
            condition = build_condition(spec)
            results.append(condition.evaluate(context))
        if alert.match_mode == MatchMode.ANY:
            matched = any(results)
        else:
            matched = all(results)
        self._previous_prices[symbol] = price
        if change is not None:
            self._previous_changes[symbol] = change
        return matched

    @staticmethod
    def _percent_change(previous_price: float | None, price: float) -> float | None:
        if previous_price is None or previous_price == 0:
            return None
        return (price - previous_price) / previous_price * 100

    async def _expire_if_needed(self, alert: Alert) -> None:
        if (
            alert.status is AlertStatus.ACTIVE
            and alert.expires_at is not None
            and alert.expires_at <= self._clock()
        ):
            alert.status = AlertStatus.EXPIRED
            await self.repository.update(alert)

    async def _raise_if_expired(self, alert: Alert) -> None:
        if alert.expires_at is not None and alert.expires_at <= self._clock():
            alert.status = AlertStatus.EXPIRED
            await self.repository.update(alert)
            raise AlertExpired()

    def _default_message(self, request: CreateAlertRequest) -> str:
        descriptions = [c.to_spec().describe() for c in request.conditions]
        joiner = " AND " if request.match_mode == MatchMode.ALL else " OR "
        return f"{request.symbol} {joiner.join(descriptions)}"