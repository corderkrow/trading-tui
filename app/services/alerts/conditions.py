"""Condition strategies — Strategy pattern for rule evaluation."""

from __future__ import annotations

from typing import Protocol

from app.services.alerts.domain import ConditionSpec, MarketContext, Operator


class Condition(Protocol):
    spec: ConditionSpec

    def evaluate(self, context: MarketContext) -> bool: ...


class PriceAboveCondition:
    def __init__(self, spec: ConditionSpec):
        self.spec = spec

    def evaluate(self, context: MarketContext) -> bool:
        return context.price > self.spec.value


class PriceBelowCondition:
    def __init__(self, spec: ConditionSpec):
        self.spec = spec

    def evaluate(self, context: MarketContext) -> bool:
        return context.price < self.spec.value


class PriceCrossingCondition:
    """Detects a price transition through the target value.

    Crossing requires previous state: without history the condition cannot
    fire (first evaluation only establishes a baseline).
    """

    def __init__(self, spec: ConditionSpec):
        self.spec = spec

    def evaluate(self, context: MarketContext) -> bool:
        if context.previous_price is None:
            return False
        target = self.spec.value
        crossed_up = context.previous_price < target and context.price >= target
        crossed_down = context.previous_price > target and context.price <= target
        return crossed_up or crossed_down


def build_condition(spec: ConditionSpec) -> Condition:
    """Factory mapping a ConditionSpec to its strategy implementation."""
    strategies: dict[Operator, type[Condition]] = {
        Operator.ABOVE: PriceAboveCondition,
        Operator.BELOW: PriceBelowCondition,
        Operator.CROSSING: PriceCrossingCondition,
    }
    try:
        strategy_cls = strategies[spec.operator]
    except KeyError:
        from app.services.alerts.errors import InvalidAlertCondition

        raise InvalidAlertCondition(f"Unsupported operator: {spec.operator}") from None
    return strategy_cls(spec)