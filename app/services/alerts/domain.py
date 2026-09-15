"""Alert domain model — persistence- and UI-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def now_utc() -> datetime:
    """Timezone-aware current time. Never naive."""
    return datetime.now(timezone.utc)


class AlertStatus(StrEnum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"


class TriggerMode(StrEnum):
    ONCE = "ONCE"
    EVERY_TIME = "EVERY_TIME"


class MatchMode(StrEnum):
    ALL = "ALL"
    ANY = "ANY"


class Operator(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    CROSSING = "crossing"
    RISES_BY = "rises_by"
    FALLS_BY = "falls_by"
    TURNS_POSITIVE = "turns_positive"
    TURNS_NEGATIVE = "turns_negative"


OPERATOR_LABEL: dict[Operator, str] = {
    Operator.ABOVE: "Above",
    Operator.BELOW: "Below",
    Operator.CROSSING: "Crossing",
    Operator.RISES_BY: "Rises by",
    Operator.FALLS_BY: "Falls by",
    Operator.TURNS_POSITIVE: "Turns positive",
    Operator.TURNS_NEGATIVE: "Turns negative",
}

# Metrics tracked between consecutive price ticks (percent change, ...).
CHANGE_METRIC = "change_pct"
CHANGE_METRICS = frozenset({CHANGE_METRIC})


@dataclass(frozen=True)
class ConditionSpec:
    """Serializable description of one condition (metric + operator + value)."""

    operator: Operator
    value: float
    metric: str = "price"

    def describe(self) -> str:
        if self.metric in CHANGE_METRICS:
            formatted = _format_percent(self.value)
        else:
            formatted = _format_value(self.value)
        return f"{OPERATOR_LABEL[self.operator]} {formatted}"


def _format_value(value: float) -> str:
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _format_percent(value: float) -> str:
    if value == int(value):
        return f"{int(value)}%"
    return f"{value:.2f}%"


@dataclass
class Alert:
    id: str = field(default_factory=lambda: uuid4().hex)
    symbol: str = ""
    conditions: list[ConditionSpec] = field(default_factory=list)
    match_mode: MatchMode = MatchMode.ALL
    trigger_mode: TriggerMode = TriggerMode.ONCE
    expires_at: datetime | None = None
    message: str = ""
    notification_channels: list[str] = field(default_factory=lambda: ["in_app"])
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: datetime = field(default_factory=now_utc)
    triggered_at: datetime | None = None
    last_evaluated_at: datetime | None = None


@dataclass(frozen=True)
class MarketContext:
    """Snapshot of market data handed to condition strategies."""

    symbol: str
    price: float
    previous_price: float | None = None
    change: float | None = None
    previous_change: float | None = None
    at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class AlertEvent:
    """Fired when an alert matches its conditions."""

    alert_id: str
    symbol: str
    message: str
    conditions: tuple[ConditionSpec, ...]
    triggered_at: datetime = field(default_factory=now_utc)