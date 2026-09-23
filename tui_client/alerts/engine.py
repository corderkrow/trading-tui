"""Alert evaluation — pure logic, **no Textual imports**.

Multi-condition semantics: an alert fires only when **all** conditions are true
at once (AND). There is no OR.

Crossing caveat (v1)
--------------------
A crossing is an *event*: it is true only on the step it happens. Two crossings
therefore almost never report true on the same step, so AND-combining them is
unlikely to fire. v1 evaluates each condition as its **current boolean state**
and does not latch crossings; latching a crossing as true for the remainder of
the current check window is left for a later revision.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tui_client.alerts.models import TF_SECONDS, AlertSpec, Condition


@runtime_checkable
class PriceFeed(Protocol):
    """Minimal market-data surface the evaluator needs — mockable in tests."""

    async def get(self, symbol: str, source: str, timeframe: str) -> float:
        """Latest value for *source* on *timeframe* for *symbol*."""
        ...


def check_interval(spec: AlertSpec) -> int:
    """Poll interval in seconds — the smallest timeframe used by any condition."""
    return min(TF_SECONDS[c.timeframe] for c in spec.conditions)


def eval_condition(c: Condition, prev: float, cur: float, ref: float) -> bool:
    """Evaluate one condition for the current state.

    ``prev``/``cur`` are the reference value's previous and current reading,
    ``ref`` the condition target. Crossing operators need ``prev``; the others
    ignore it.
    """
    operator = c.operator
    if operator == "Crossing":
        return (prev - ref) * (cur - ref) < 0 or cur == ref
    if operator == "Crossing up":
        return prev < ref <= cur
    if operator == "Crossing down":
        return prev > ref >= cur
    if operator == "Greater than":
        return cur > ref
    if operator == "Less than":
        return cur < ref
    return False


def should_fire(states: list[bool]) -> bool:
    """AND-combine per-condition states; an empty list never fires."""
    return len(states) > 0 and all(states)
