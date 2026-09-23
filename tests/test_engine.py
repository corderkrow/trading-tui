"""Tests for the alert evaluation engine (no Textual)."""

from __future__ import annotations

from tui_client.alerts.engine import check_interval, eval_condition, should_fire
from tui_client.alerts.models import AlertSpec, Condition


def cond(operator: str, timeframe: str = "1m", value: float = 100.0) -> Condition:
    return Condition("Price", operator, "Value", value, timeframe)


def spec(*timeframes: str) -> AlertSpec:
    return AlertSpec(
        symbol="BTCUSD",
        conditions=[cond("Crossing", tf) for tf in timeframes],
        trigger="Once only",
        expires_at=None,  # type: ignore[arg-type]
        message="",
        notifications=[],
    )


def test_check_interval_uses_smallest_timeframe():
    assert check_interval(spec("1h", "15m", "1m")) == 60
    assert check_interval(spec("4h")) == 14400
    assert check_interval(spec("1D", "30m")) == 1800


def test_crossing_fires_on_transition_either_way():
    condition = cond("Crossing", value=100.0)
    assert eval_condition(condition, prev=99.0, cur=101.0, ref=100.0)
    assert eval_condition(condition, prev=101.0, cur=99.0, ref=100.0)
    # landing exactly on the reference counts as a crossing
    assert eval_condition(condition, prev=101.0, cur=100.0, ref=100.0)


def test_crossing_does_not_fire_when_moving_away():
    condition = cond("Crossing", value=100.0)
    assert not eval_condition(condition, prev=100.0, cur=101.0, ref=100.0)
    assert not eval_condition(condition, prev=99.0, cur=98.0, ref=100.0)


def test_crossing_up_and_down():
    up = cond("Crossing up", value=100.0)
    assert eval_condition(up, prev=99.0, cur=100.0, ref=100.0)
    assert eval_condition(up, prev=99.0, cur=150.0, ref=100.0)
    assert not eval_condition(up, prev=100.0, cur=101.0, ref=100.0)

    down = cond("Crossing down", value=100.0)
    assert eval_condition(down, prev=101.0, cur=100.0, ref=100.0)
    assert eval_condition(down, prev=101.0, cur=99.0, ref=100.0)
    assert not eval_condition(down, prev=100.0, cur=99.0, ref=100.0)


def test_greater_and_less_than():
    greater = cond("Greater than", value=100.0)
    assert eval_condition(greater, prev=0.0, cur=101.0, ref=100.0)
    assert not eval_condition(greater, prev=0.0, cur=100.0, ref=100.0)

    less = cond("Less than", value=100.0)
    assert eval_condition(less, prev=0.0, cur=99.0, ref=100.0)
    assert not eval_condition(less, prev=0.0, cur=100.0, ref=100.0)


def test_unknown_operator_never_fires():
    assert not eval_condition(cond("Sideways"), prev=0.0, cur=1.0, ref=1.0)


def test_should_fire_is_and_and_rejects_empty():
    assert should_fire([True, True, True])
    assert not should_fire([True, False, True])
    assert not should_fire([False])
    assert not should_fire([])
