"""Data model for multi-condition alerts.

Pure data — no Textual imports — so the model (and :mod:`alerts.engine`) can be
unit-tested and reused by any front-end.

Reference: https://www.tradingview.com/support/solutions/43000761492-multi-condition-alerts/

Rules encoded here:

* 1–5 conditions per alert (:data:`MAX_CONDITIONS`).
* Every condition shares one symbol (the dialog header symbol).
* Conditions may use different timeframes; :mod:`alerts.engine` derives the
  poll interval from the smallest one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

MAX_CONDITIONS = 5

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]
TF_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1D": 86400,
}
DEFAULT_TIMEFRAME = TIMEFRAMES[0]

# Option lists used by the editor. RSI / MA / Drawing are stubs in v1 (no data
# behind them yet) but kept in the model so later revisions stay additive.
SOURCES = ["Price", "Volume", "RSI", "MA", "Drawing"]
OPERATORS = ["Crossing", "Crossing up", "Crossing down", "Greater than", "Less than"]
VALUE_TYPES = ["Value", "Indicator"]

TRIGGERS = ["Once only", "Once per bar", "Once per bar close", "Once per minute"]

NOTIFICATIONS = ["App", "Toasts", "Sound", "Email", "Webhook"]
DEFAULT_NOTIFICATIONS = ["App", "Toasts", "Sound"]

# UI intent -> backend vocabulary. The multi-condition editor ships ahead of the
# evaluator, which only tracks price / percent-change metrics, so every source
# approximates to a price metric (same reduction the legacy dialog used).
OPERATOR_BACKEND: dict[str, tuple[str, str]] = {
    "Crossing": ("crossing", "price"),
    "Crossing up": ("crossing", "price"),
    "Crossing down": ("crossing", "price"),
    "Greater than": ("above", "price"),
    "Less than": ("below", "price"),
}
TRIGGER_BACKEND = {
    "Once only": "ONCE",
    "Once per bar": "EVERY_TIME",
    "Once per bar close": "EVERY_TIME",
    "Once per minute": "EVERY_TIME",
}
NOTIFICATION_BACKEND = {
    "App": "in_app",
    "Toasts": "toast",
    "Sound": "sound",
    "Email": "email",
    "Webhook": "webhook",
}

# Backend -> UI (used when editing an existing alert back into the dialog).
OPERATOR_UI: dict[tuple[str, str], str] = {
    ("crossing", "price"): "Crossing",
    ("above", "price"): "Greater than",
    ("below", "price"): "Less than",
    ("rises_by", "change_pct"): "Greater than",
    ("falls_by", "change_pct"): "Less than",
    ("turns_positive", "price"): "Crossing up",
    ("turns_negative", "price"): "Crossing down",
}
TRIGGER_UI = {"ONCE": "Once only", "EVERY_TIME": "Once per bar"}
NOTIFICATION_UI = {backend: ui for ui, backend in NOTIFICATION_BACKEND.items()}


def format_value(value: float | None) -> str:
    """Human-readable numeric value; ``—`` when the condition has none."""
    return f"{value:,.2f}" if value is not None else "—"


@dataclass
class Condition:
    """One leg of a multi-condition alert."""

    source: str
    operator: str
    value_type: str
    value: float | None
    timeframe: str = DEFAULT_TIMEFRAME
    id: str = field(default_factory=lambda: uuid4().hex[:8])

    def preview(self) -> str:
        """Full preview shown on the condition button (includes timeframe)."""
        return f"{self.source} {self.operator} {format_value(self.value)} · {self.timeframe}"

    def preview_short(self) -> str:
        """Preview without the timeframe, used in the default alert message."""
        return f"{self.source} {self.operator} {format_value(self.value)}"

    def to_payload(self) -> dict:
        """Translate into the backend ``ConditionRequest`` shape."""
        operator, metric = OPERATOR_BACKEND.get(self.operator, ("crossing", "price"))
        return {"metric": metric, "operator": operator, "value": self.value}

    @classmethod
    def from_payload(cls, data: dict) -> "Condition":
        """Rebuild a UI condition from a backend condition dict."""
        metric = data.get("metric", "price")
        operator = data.get("operator", "crossing")
        value = data.get("value")
        return cls(
            source="Price",
            operator=OPERATOR_UI.get((operator, metric), "Crossing"),
            value_type="Value" if value is not None else "Indicator",
            value=float(value) if value is not None else None,
        )


@dataclass
class AlertSpec:
    """A validated multi-condition alert.

    ``conditions`` is always a list (a single-condition alert is a list of one);
    there is no separate code path for the one-condition case.
    """

    symbol: str
    conditions: list[Condition]
    trigger: str
    expires_at: datetime
    message: str
    notifications: list[str]

    def to_payload(self) -> dict:
        """Translate into the backend ``CreateAlertRequest`` shape."""
        return {
            "symbol": self.symbol.strip().upper(),
            "conditions": [condition.to_payload() for condition in self.conditions],
            "match_mode": "ALL",
            "trigger_mode": TRIGGER_BACKEND.get(self.trigger, "ONCE"),
            "expires_at": self.expires_at.isoformat(),
            "message": self.message or None,
            "notification_channels": [
                NOTIFICATION_BACKEND[name]
                for name in self.notifications
                if name in NOTIFICATION_BACKEND
            ],
        }

    @classmethod
    def from_view(cls, view) -> "AlertSpec":
        """Rebuild a dialog spec from an ``AlertView`` (used to edit alerts)."""
        conditions = [Condition.from_payload(c) for c in view.conditions]
        if not conditions:
            conditions = [
                Condition(source="Price", operator="Crossing", value_type="Value", value=None)
            ]
        expires = None
        if view.expires_at:
            try:
                expires = datetime.fromisoformat(view.expires_at)
            except ValueError:
                expires = None
        if expires is None:
            expires = datetime.now().astimezone() + timedelta(days=30)
        notifications = [
            NOTIFICATION_UI[name]
            for name in view.notification_channels
            if name in NOTIFICATION_UI
        ] or list(DEFAULT_NOTIFICATIONS)
        return cls(
            symbol=view.symbol,
            conditions=conditions,
            trigger=TRIGGER_UI.get(view.trigger_mode, "Once only"),
            expires_at=expires,
            message=view.message,
            notifications=notifications,
        )
