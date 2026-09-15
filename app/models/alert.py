"""Pydantic DTOs for the alerts REST API.

Kept separate from the domain model (`app.services.alerts.domain`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.alerts.domain import (
    Alert,
    AlertEvent,
    AlertStatus,
    ConditionSpec,
    MatchMode,
    Operator,
    TriggerMode,
    now_utc,
)


class ConditionRequest(BaseModel):
    metric: Literal["price", "change_pct"] = "price"
    operator: Operator
    value: float = Field(
        ...,
        gt=0,
        description="Target value, must be > 0 (percent for change-based metrics)",
    )

    def to_spec(self) -> ConditionSpec:
        return ConditionSpec(operator=self.operator, value=self.value, metric=self.metric)


class ConditionResponse(BaseModel):
    metric: str
    operator: str
    value: float

    @classmethod
    def from_spec(cls, spec: ConditionSpec) -> "ConditionResponse":
        return cls(metric=spec.metric, operator=spec.operator.value, value=spec.value)


class CreateAlertRequest(BaseModel):
    symbol: str = Field(..., min_length=1, description="Trading pair, e.g. BTCUSDT")
    conditions: list[ConditionRequest] = Field(..., min_length=1, max_length=10)
    match_mode: MatchMode = MatchMode.ALL
    trigger_mode: TriggerMode = TriggerMode.ONCE
    expires_at: datetime | None = Field(
        default=None,
        description="Timezone-aware expiration; must be in the future",
    )
    message: str | None = Field(default=None, max_length=500)
    notification_channels: list[str] = Field(
        default_factory=lambda: ["in_app"],
        min_length=1,
        description="Non-empty list of known channel names",
    )

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("Symbol must not be empty")
        return symbol

    @field_validator("expires_at")
    @classmethod
    def _validate_expiration(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Expiration must be timezone-aware (e.g. 2026-10-06T15:13:00Z)")
        if value <= now_utc():
            raise ValueError("Expiration must be in the future")
        return value


class AlertResponse(BaseModel):
    id: str
    symbol: str
    status: AlertStatus
    match_mode: MatchMode
    trigger_mode: TriggerMode
    conditions: list[ConditionResponse]
    message: str
    notification_channels: list[str]
    expires_at: datetime | None
    created_at: datetime
    triggered_at: datetime | None
    last_evaluated_at: datetime | None

    @classmethod
    def from_alert(cls, alert: Alert) -> "AlertResponse":
        return cls(
            id=alert.id,
            symbol=alert.symbol,
            status=alert.status,
            match_mode=alert.match_mode,
            trigger_mode=alert.trigger_mode,
            conditions=[ConditionResponse.from_spec(c) for c in alert.conditions],
            message=alert.message,
            notification_channels=list(alert.notification_channels),
            expires_at=alert.expires_at,
            created_at=alert.created_at,
            triggered_at=alert.triggered_at,
            last_evaluated_at=alert.last_evaluated_at,
        )


class PriceUpdateRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)


class AlertEventResponse(BaseModel):
    alert_id: str
    symbol: str
    message: str
    conditions: list[ConditionResponse]
    triggered_at: datetime

    @classmethod
    def from_event(cls, event: AlertEvent) -> "AlertEventResponse":
        return cls(
            alert_id=event.alert_id,
            symbol=event.symbol,
            message=event.message,
            conditions=[ConditionResponse.from_spec(c) for c in event.conditions],
            triggered_at=event.triggered_at,
        )