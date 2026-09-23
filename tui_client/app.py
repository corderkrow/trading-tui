"""trading-tui entry point — Textual app showing the alerts console."""

from __future__ import annotations

import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx
from textual.app import App

from tui_client.api import AlertApiClient, HttpAlertApi, set_currency
from tui_client.monitor import PriceChangeMonitor, event_message
from tui_client.screens.alert_list import AlertListScreen
from tui_client.screens.prices import PricesScreen, DEFAULT_WATCHLIST
from tui_client.screens.settings import SettingsModal
from tui_client.settings import UserSettings, save_settings, user_settings
from tui_client.themes import CODERKROW_DARK

CSS = """
/* Colors come from the active Textual theme — default: coderkrow dark
   (tui_client/themes.py, brand tokens in .ai/rules/brand/RULES.md). */

AlertListScreen {
    layout: vertical;
}

/* ── Tables ─────────────────────────────────────────── */
DataTable {
    height: 1fr;
    border: round $accent 70%;
    scrollbar-gutter: stable;
}
DataTable:focus {
    border: round $accent;
}
DataTable > .datatable--header {
    background: $panel;
    color: $foreground;
    text-style: bold;
}
DataTable > .datatable--header-cursor,
DataTable > .datatable--header-hover {
    background: $accent 60%;
    color: $foreground;
}
DataTable > .datatable--odd-row {
    background: $panel 35%;
}
DataTable > .datatable--even-row {
    background: $panel 75%;
}
DataTable > .datatable--cursor,
DataTable > .datatable--fixed-cursor,
DataTable:focus > .datatable--cursor,
DataTable:focus > .datatable--fixed-cursor {
    background: $primary 30%;
    color: $foreground;
    text-style: bold;
}
DataTable > .datatable--hover {
    background: $primary 12%;
}

/* ── Prices screen ──────────────────────────────────── */
#mode-label {
    padding: 0 2;
    color: $text;
    background: $surface;
    border-bottom: solid $panel;
}

#watchlist-tabs {
    padding: 0 2;
    color: $text-muted;
    background: $surface;
}

#mode-tabs {
    background: $surface;
}

/* ── Create-alert modal ─────────────────────────────── */
#modal-body {
    width: 62;
    height: auto;
    max-height: 90%;
    border: round $accent 80%;
    background: $surface;
    padding: 1 2;
}
#modal-title {
    text-style: bold;
    margin-bottom: 1;
}
.field-label {
    margin-top: 1;
}
.error {
    color: $error;
}
#conditions {
    height: auto;
    max-height: 12;
    border: solid $accent 30%;
    margin: 1 0;
}
#conditions Horizontal {
    height: auto;
}
#modal-actions {
    height: auto;
    margin-top: 1;
}
#modal-actions Button {
    margin-right: 1;
}
"""


class AlertsApp(App[None]):
    TITLE = "trading-tui"
    SUB_TITLE = "live market desk"
    CSS = CSS

    def __init__(
        self,
        api: AlertApiClient | None = None,
        default_symbol: str = "BTCUSDT",
        user: UserSettings | None = None,
    ) -> None:
        super().__init__()
        self.register_theme(CODERKROW_DARK)
        self.api = api or HttpAlertApi()
        self.default_symbol = default_symbol
        self.user = user or user_settings
        self.monitor = PriceChangeMonitor(
            self.api, lambda: self.user, self._on_price_change
        )

    def on_mount(self) -> None:
        self.theme = CODERKROW_DARK.name
        self.alerts_screen = AlertListScreen(self.api, default_symbol=self.default_symbol)
        wl = self.user.watchlist
        self.prices_screen = PricesScreen(
            self.api,
            watchlists=dict(wl.watchlists),
            active_watchlist=wl.active,
            on_watchlist_change=self._on_watchlist_change,
            watchlist_mode=wl.mode,
            display=self.user.display,
        )
        self.push_screen(self.prices_screen)
        self.run_worker(self.monitor.run(), exclusive=True, group="price-monitor")

    def _on_watchlist_change(self, name: str, symbols: list[str]) -> None:
        """Persist a newly created watchlist to user settings."""
        self.user.watchlist.watchlists[name] = list(symbols)
        self.user.watchlist.active = name
        save_settings(self.user)

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(self.user), callback=self._on_settings_saved)

    def _apply_display(self, display) -> None:
        """Push display settings to already-mounted screens."""
        if self.prices_screen.is_mounted:
            self.prices_screen.apply_display(display)

    def _on_settings_saved(self, updated: UserSettings | None) -> None:
        if updated is None:
            return
        self.user = updated
        self._apply_display(updated.display)
        ps = self.prices_screen
        ps.watchlist_mode = updated.watchlist.mode
        ps.watchlists = dict(updated.watchlist.watchlists)
        ps.active_watchlist = updated.watchlist.active
        ps.watchlist = list(updated.watchlist.active_symbols())
        ps.run_worker(ps.reload())

    async def _on_price_change(self, symbol: str, change: float, threshold: float) -> None:
        self.notify(event_message(symbol, change, threshold))

    async def on_unmount(self) -> None:
        close = getattr(self.api, "close", None)
        if close is not None:
            await close()


def _server_alive(base_url: str) -> bool:
    try:
        resp = httpx.get(f"{base_url}/alerts", timeout=0.5)
        return resp.status_code < 500
    except httpx.HTTPError:
        return False


def _spawn_api(base_url: str) -> subprocess.Popen | None:
    """Start the FastAPI server in the background if it isn't already running."""
    port = urlparse(base_url).port or 8333
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):  # ~5s to boot
        if _server_alive(base_url):
            return proc
        time.sleep(0.25)
    return proc


def main() -> None:
    from app.config import settings

    set_currency(settings.CURRENCY.lower())
    api = HttpAlertApi()
    server: subprocess.Popen | None = None
    if isinstance(api, HttpAlertApi) and not _server_alive(api.base_url):
        server = _spawn_api(api.base_url)
    try:
        AlertsApp(api=api).run()
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()