"""Shared test helpers."""

from datetime import datetime, timedelta, timezone


class FakeClock:
    """Mutable clock for deterministic expiry/evaluation tests."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2090, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)