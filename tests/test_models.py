"""Tests for the alert data model (no Textual)."""

from __future__ import annotations

from tui_client.alerts.models import (
    DEFAULT_TIMEFRAME,
    MAX_CONDITIONS,
    TF_SECONDS,
    TIMEFRAMES,
    AlertSpec,
    Condition,
)


def test_preview_includes_value_and_timeframe():
    condition = Condition(
        source="Price",
        operator="Crossing",
        value_type="Value",
        value=80576.76,
        timeframe="1h",
    )
    assert condition.preview() == "Price Crossing 80,576.76 · 1h"


def test_preview_handles_missing_value():
    condition = Condition(
        source="RSI",
        operator="Less than",
        value_type="Indicator",
        value=None,
        timeframe="15m",
    )
    assert condition.preview() == "RSI Less than — · 15m"
    assert condition.preview_short() == "RSI Less than —"


def test_preview_short_omits_timeframe():
    condition = Condition("Price", "Greater than", "Value", 1000.0, "1m")
    assert condition.preview_short() == "Price Greater than 1,000.00"


def test_condition_ids_are_unique_and_short():
    first = Condition("Price", "Crossing", "Value", 1.0)
    second = Condition("Price", "Crossing", "Value", 1.0)
    assert first.id != second.id
    assert len(first.id) == 8


def test_default_timeframe_is_first():
    assert DEFAULT_TIMEFRAME == TIMEFRAMES[0]
    assert Condition("Price", "Crossing", "Value", 1.0).timeframe == DEFAULT_TIMEFRAME


def test_constants_are_consistent():
    assert MAX_CONDITIONS == 5
    assert set(TIMEFRAMES) == set(TF_SECONDS)
    assert TF_SECONDS["1h"] == 3600


def test_alert_spec_holds_condition_list():
    condition = Condition("Price", "Crossing", "Value", 1.0)
    spec = AlertSpec(
        symbol="BTCUSD",
        conditions=[condition],
        trigger="Once only",
        expires_at=None,  # type: ignore[arg-type]
        message="BTCUSD Price Crossing 1.00",
        notifications=["App"],
    )
    assert spec.conditions == [condition]


def test_payload_round_trip_through_view():
    from datetime import datetime, timedelta

    from tui_client.api import AlertView

    spec = AlertSpec(
        symbol="btcusdt",
        conditions=[Condition("Price", "Greater than", "Value", 100.0)],
        trigger="Once only",
        expires_at=datetime.now().astimezone() + timedelta(days=1),
        message="BTCUSDT Above 100",
        notifications=["App", "Toasts"],
    )
    payload = spec.to_payload()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["conditions"] == [
        {"metric": "price", "operator": "above", "value": 100.0}
    ]
    assert payload["trigger_mode"] == "ONCE"
    assert payload["notification_channels"] == ["in_app", "toast"]

    view = AlertView(
        id="a1",
        symbol="BTCUSDT",
        status="ACTIVE",
        conditions=payload["conditions"],
        message=payload["message"] or "",
        expires_at=payload["expires_at"],
        trigger_mode=payload["trigger_mode"],
        notification_channels=payload["notification_channels"],
    )
    rebuilt = AlertSpec.from_view(view)
    assert rebuilt.symbol == "BTCUSDT"
    assert rebuilt.conditions[0].operator == "Greater than"
    assert rebuilt.conditions[0].value == 100.0
    assert rebuilt.trigger == "Once only"
    assert rebuilt.notifications == ["App", "Toasts"]
    assert rebuilt.to_payload()["conditions"] == payload["conditions"]
