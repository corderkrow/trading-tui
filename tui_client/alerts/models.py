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
from datetime import datetime
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
