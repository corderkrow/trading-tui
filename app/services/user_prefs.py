"""Read the TUI's user-settings JSON for server-side alert delivery filtering.

The TUI persists user preferences to a JSON file; the API server (spawned by
the TUI on the same machine) reads only the delivery preference from it.
Missing/corrupt file → None (no filtering, per-alert channels win).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DELIVERY_CHANNELS: dict[str, set[str]] = {
    "push": {"push"},
    "in_app": {"in_app"},
    "push_email": {"push", "email"},
    "none": set(),
}


def settings_path() -> Path:
    return Path(
        os.environ.get(
            "TRADING_TUI_SETTINGS", "~/.config/trading-tui/settings.json"
        )
    ).expanduser()


_cache: tuple[Path, int, set[str] | None] | None = None


def allowed_channels(path: Path | None = None) -> set[str] | None:
    """Channels permitted by the delivery pref; None means "no pref".

    Called on every notification dispatch, so the parsed result is cached and
    only re-read when the file's mtime changes.
    """
    resolved = path or settings_path()
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        return None
    global _cache
    if _cache is not None and _cache[0] == resolved and _cache[1] == mtime:
        return _cache[2]
    result = _read_allowed_channels(resolved)
    _cache = (resolved, mtime, result)
    return result


def _read_allowed_channels(path: Path) -> set[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        delivery = data["notifications"]["price_alert_delivery"]
        return DELIVERY_CHANNELS[delivery]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, OSError):
        return None
