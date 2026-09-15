"""Condition strategy tests — including crossing edge cases."""

from app.services.alerts.conditions import build_condition
from app.services.alerts.domain import ConditionSpec, MarketContext, Operator


def cond(operator: Operator, value: float):
    return build_condition(ConditionSpec(operator=operator, value=value))


def ctx(price: float, previous: float | None = None) -> MarketContext:
    return MarketContext(symbol="BTCUSDT", price=price, previous_price=previous)


def test_above_fires_only_above_target():
    c = cond(Operator.ABOVE, 100)
    assert c.evaluate(ctx(101))
    assert not c.evaluate(ctx(100))  # equality is not "above"
    assert not c.evaluate(ctx(99))


def test_below_fires_only_below_target():
    c = cond(Operator.BELOW, 100)
    assert c.evaluate(ctx(99))
    assert not c.evaluate(ctx(100))
    assert not c.evaluate(ctx(101))


def test_crossing_requires_history():
    c = cond(Operator.CROSSING, 100)
    assert not c.evaluate(ctx(101, previous=None))  # first tick = baseline only


def test_crossing_up_transition():
    c = cond(Operator.CROSSING, 100)
    # previous below target, current at/above -> crossed
    assert c.evaluate(ctx(100, previous=99))
    assert c.evaluate(ctx(101, previous=99))
    assert c.evaluate(ctx(150, previous=99))


def test_crossing_down_transition():
    c = cond(Operator.CROSSING, 100)
    assert c.evaluate(ctx(100, previous=101))
    assert c.evaluate(ctx(99, previous=101))


def test_no_crossing_when_moving_away():
    c = cond(Operator.CROSSING, 100)
    # start at target, move away: no transition through it
    assert not c.evaluate(ctx(101, previous=100))
    assert not c.evaluate(ctx(99, previous=100))


def test_no_crossing_without_crossing_the_target():
    c = cond(Operator.CROSSING, 100)
    assert not c.evaluate(ctx(99, previous=98))
    assert not c.evaluate(ctx(101, previous=102))
    assert not c.evaluate(ctx(99, previous=99))
    assert not c.evaluate(ctx(101, previous=101))


def ctx_change(
    price: float,
    change: float | None,
    previous_change: float | None = None,
) -> MarketContext:
    return MarketContext(
        symbol="BTCUSDT",
        price=price,
        change=change,
        previous_change=previous_change,
    )


def test_rises_by_requires_history():
    c = cond(Operator.RISES_BY, 2)
    assert not c.evaluate(ctx_change(102, change=None))


def test_rises_by_percent_threshold():
    c = cond(Operator.RISES_BY, 2)
    assert not c.evaluate(ctx_change(101, change=1.99))
    assert c.evaluate(ctx_change(102, change=2.0))
    assert c.evaluate(ctx_change(120, change=20.0))


def test_falls_by_percent_threshold():
    c = cond(Operator.FALLS_BY, 2)
    assert not c.evaluate(ctx_change(98, change=-1.99))
    assert c.evaluate(ctx_change(98, change=-2.0))
    assert c.evaluate(ctx_change(80, change=-20.0))


def test_falls_by_ignores_rise():
    c = cond(Operator.FALLS_BY, 2)
    assert not c.evaluate(ctx_change(110, change=10.0))


def test_turns_positive_requires_two_changes():
    c = cond(Operator.TURNS_POSITIVE, 1)
    assert not c.evaluate(ctx_change(101, change=1.0, previous_change=None))


def test_turns_positive():
    c = cond(Operator.TURNS_POSITIVE, 1)
    # negative -> positive
    assert c.evaluate(ctx_change(101, change=1.0, previous_change=-0.5))
    # zero -> positive
    assert c.evaluate(ctx_change(100, change=0.5, previous_change=0.0))
    # stays positive: no fire
    assert not c.evaluate(ctx_change(102, change=2.0, previous_change=1.0))
    # still negative: no fire
    assert not c.evaluate(ctx_change(99, change=-1.0, previous_change=-2.0))


def test_turns_negative():
    c = cond(Operator.TURNS_NEGATIVE, 1)
    # positive -> negative
    assert c.evaluate(ctx_change(99, change=-1.0, previous_change=0.5))
    # zero -> negative
    assert c.evaluate(ctx_change(99, change=-0.5, previous_change=0.0))
    # stays negative: no fire
    assert not c.evaluate(ctx_change(97, change=-3.0, previous_change=-2.0))
    # still positive: no fire
    assert not c.evaluate(ctx_change(103, change=3.0, previous_change=1.0))


def test_describe_percent_values():
    spec = ConditionSpec(operator=Operator.RISES_BY, value=5, metric="change_pct")
    assert spec.describe() == "Rises by 5%"
    spec = ConditionSpec(operator=Operator.RISES_BY, value=5.25, metric="change_pct")
    assert spec.describe() == "Rises by 5.25%"