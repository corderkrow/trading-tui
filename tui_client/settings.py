"""User settings — watchlists + notification prefs, persisted to JSON."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tui_client.screens.prices import DEFAULT_WATCHLIST

ThresholdSource = Literal["watchlist", "portfolio", "both"]
DeliveryType = Literal["push", "in_app", "push_email", "none"]
WatchlistMode = Literal["single", "multiple"]

SETTINGS_PATH = Path(
    os.environ.get("TRADING_TUI_SETTINGS", "~/.config/trading-tui/settings.json")
).expanduser()


class WatchlistSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    mode: WatchlistMode = "single"
    watchlists: dict[str, list[str]] = Field(
        default_factory=lambda: {"default": list(DEFAULT_WATCHLIST)}
    )
    active: str = "default"

    @field_validator("watchlists")
    @classmethod
    def _non_empty_lists(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        cleaned = {name: [s.upper() for s in symbols] for name, symbols in v.items()}
        if not cleaned:
            raise ValueError("at least one watchlist required")
        return cleaned

    @model_validator(mode="after")
    def _active_exists(self) -> "WatchlistSettings":
        if self.active not in self.watchlists:
            self.active = next(iter(self.watchlists))
        return self

    def active_symbols(self) -> list[str]:
        return self.watchlists[self.active]


class NotificationSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    price_change_sources: ThresholdSource = "watchlist"
    price_change_thresholds: list[float] = Field(default_factory=lambda: [2.0, 5.0, 20.0])
    custom_threshold: float | None = None
    price_alert_delivery: DeliveryType = "in_app"

    @field_validator("price_change_thresholds")
    @classmethod
    def _valid_thresholds(cls, v: list[float]) -> list[float]:
        cleaned = sorted({float(x) for x in v if 0 < float(x) <= 100})
        if not cleaned:
            raise ValueError("at least one threshold required")
        return cleaned

    @field_validator("custom_threshold")
    @classmethod
    def _valid_custom(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not 0 < v <= 100:
            raise ValueError("custom threshold must be in (0, 100]")
        return v

    def enabled_thresholds(self) -> list[float]:
        thresholds = list(self.price_change_thresholds)
        if self.custom_threshold is not None:
            thresholds.append(self.custom_threshold)
        return sorted(set(thresholds))


class UserSettings(BaseModel):
    watchlist: WatchlistSettings = Field(default_factory=WatchlistSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)


def load_settings(path: Path = SETTINGS_PATH) -> UserSettings:
    """Load settings from JSON; fall back to defaults on missing/corrupt file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserSettings.model_validate(data)
    except FileNotFoundError:
        return UserSettings()
    except (json.JSONDecodeError, ValueError):
        return UserSettings()


def save_settings(settings: UserSettings, path: Path = SETTINGS_PATH) -> None:
    """Atomically persist settings (tmp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump_json(indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


user_settings = load_settings()
