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
