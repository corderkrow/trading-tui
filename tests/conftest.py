"""Shared test helpers."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Tests must not read the developer's real ~/.config/trading-tui/settings.json
# (its watchlist may be empty or customized). Point the settings path at a
# fresh empty file so load_settings() falls back to defaults. Must run before
# tui_client.settings is imported.
os.environ.setdefault(
    "TRADING_TUI_SETTINGS",
    str(Path(tempfile.mkdtemp(prefix="trading-tui-tests-")) / "settings.json"),
)


class FakeClock:
    """Mutable clock for deterministic expiry/evaluation tests."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2090, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)