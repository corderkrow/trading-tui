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


class _ChangePercentCondition:
    """Base for conditions over percent change between consecutive ticks."""

    def __init__(self, spec: ConditionSpec):
        self.spec = spec

    def evaluate(self, context: MarketContext) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError


class PriceRisesByCondition(_ChangePercentCondition):
    """Fires when price compared to the previous tick rose by >= value percent."""

    def evaluate(self, context: MarketContext) -> bool:
        return context.change is not None and context.change >= self.spec.value


class PriceFallsByCondition(_ChangePercentCondition):
    """Fires when price compared to the previous tick fell by >= value percent."""

    def evaluate(self, context: MarketContext) -> bool:
        return context.change is not None and context.change <= -self.spec.value


class PriceTurnsPositiveCondition(_ChangePercentCondition):
    """Fires when the percent change turns positive (<= 0 on the previous tick)."""

    def evaluate(self, context: MarketContext) -> bool:
        if context.previous_change is None or context.change is None:
            return False
        return context.previous_change <= 0 and context.change > 0


class PriceTurnsNegativeCondition(_ChangePercentCondition):
    """Fires when the percent change turns negative (>= 0 on the previous tick)."""

    def evaluate(self, context: MarketContext) -> bool:
        if context.previous_change is None or context.change is None:
            return False
        return context.previous_change >= 0 and context.change < 0


def build_condition(spec: ConditionSpec) -> Condition:
    """Factory mapping a ConditionSpec to its strategy implementation."""
    strategies: dict[Operator, type[Condition]] = {
        Operator.ABOVE: PriceAboveCondition,
        Operator.BELOW: PriceBelowCondition,
        Operator.CROSSING: PriceCrossingCondition,
        Operator.RISES_BY: PriceRisesByCondition,
        Operator.FALLS_BY: PriceFallsByCondition,
        Operator.TURNS_POSITIVE: PriceTurnsPositiveCondition,
        Operator.TURNS_NEGATIVE: PriceTurnsNegativeCondition,
    }
    try:
        strategy_cls = strategies[spec.operator]
    except KeyError:
        from app.services.alerts.errors import InvalidAlertCondition

        raise InvalidAlertCondition(f"Unsupported operator: {spec.operator}") from None
    return strategy_cls(spec)