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