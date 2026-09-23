"""Multi-condition alerts (TradingView-style).

Package split:

* :mod:`tui_client.alerts.models` — dataclasses + constants (no Textual).
* :mod:`tui_client.alerts.engine` — evaluation logic + ``PriceFeed`` protocol.
* :mod:`tui_client.alerts.widgets` — ``ConditionList`` / ``ConditionRow``.
* :mod:`tui_client.alerts.screens` — ``AlertScreen`` + sub-screens.
"""

from tui_client.alerts.models import (
    DEFAULT_NOTIFICATIONS,
    DEFAULT_TIMEFRAME,
    MAX_CONDITIONS,
    OPERATORS,
    SOURCES,
    TF_SECONDS,
    TIMEFRAMES,
    TRIGGERS,
    VALUE_TYPES,
    AlertSpec,
    Condition,
)

__all__ = [
    "AlertSpec",
    "Condition",
    "MAX_CONDITIONS",
    "TIMEFRAMES",
    "TF_SECONDS",
    "SOURCES",
    "OPERATORS",
    "VALUE_TYPES",
    "TRIGGERS",
    "DEFAULT_NOTIFICATIONS",
    "DEFAULT_TIMEFRAME",
]
