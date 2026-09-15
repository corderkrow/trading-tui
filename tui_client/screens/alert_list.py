"""Alert list screen — keyboard-driven table of alerts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Tab, Tabs

from tui_client.api import AlertApiClient, AlertView, ApiError
from tui_client.screens.create_alert import CreateAlertModal
from tui_client.screens.prices import (
    ALERT_STATE_COLORS,
    ALERT_STATE_LABELS,
    MARKET_TABS,
    SYMBOL_COLOR,
)
from tui_client.widgets import BannerHeader


class AlertListScreen(Screen[None]):
    BINDINGS = [
        Binding("n", "new_alert", "New"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "enable", "Enable"),
        Binding("d", "disable", "Disable"),
        Binding("x", "delete", "Delete"),
        Binding("p", "go_prices", "Prices"),
        Binding("o", "app.settings", "Settings"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, api: AlertApiClient, default_symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.api = api
        self.default_symbol = default_symbol
        self._alerts: list[AlertView] = []

    def compose(self) -> ComposeResult:
        yield BannerHeader()
        yield Tabs(
            *(Tab(label, id=tab_id) for tab_id, label in MARKET_TABS),
            active="a",
            id="mode-tabs",
        )
        yield DataTable(id="alerts-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("Symbol", "Condition", "Target", "Status", "Expires")
        table.cursor_type = "row"
        self.run_worker(self.reload())

    async def reload(self) -> None:
        try:
            self._alerts = await self.api.list_alerts()
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        table = self.query_one("#alerts-table", DataTable)
        table.clear()
        for alert in self._alerts:
            status_label = ALERT_STATE_LABELS.get(alert.status, alert.status.lower())
            status_color = ALERT_STATE_COLORS.get(status_label, "#ebdbb2")
            table.add_row(
                f"[{SYMBOL_COLOR}]{alert.symbol}[/]",
                alert.condition_text(),
                alert.target_text(),
                f"[{status_color}]{alert.status}[/]",
                alert.expires_text(),
            )

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if not tab_id or tab_id == "a":
            return
        prices = self.app.prices_screen
        prices.prepare_mode(tab_id)
        self.app.switch_screen(prices)

    def action_new_alert(self) -> None:
        display = getattr(self.app.user, "display", None)
        if display is not None and display.disable_custom_alerts:
            self.notify("Custom alerts are disabled in settings", severity="warning")
            return
        modal = CreateAlertModal(self.api, default_symbol=self.default_symbol)
        self.app.push_screen(modal, callback=self._on_modal_result)

    def _on_modal_result(self, payload: dict | None) -> None:
        if payload is not None:
            self.run_worker(self.reload())

    def action_refresh(self) -> None:
        self.run_worker(self.reload())

    def _selected_alert(self) -> AlertView | None:
        table = self.query_one("#alerts-table", DataTable)
        index = table.cursor_coordinate.row
        if index < 0 or index >= len(self._alerts):
            return None
        return self._alerts[index]

    def action_enable(self) -> None:
        self._mutate("enable_alert", "enabled")

    def action_disable(self) -> None:
        self._mutate("disable_alert", "disabled")

    def action_delete(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            return
        self.run_worker(self._delete(alert))

    async def _delete(self, alert: AlertView) -> None:
        try:
            await self.api.delete_alert(alert.id)
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Deleted {alert.symbol}")
        await self.reload()

    def _mutate(self, method: str, verb: str) -> None:
        alert = self._selected_alert()
        if alert is None:
            return
        self.run_worker(self._mutate_async(method, verb, alert))

    async def _mutate_async(self, method: str, verb: str, alert: AlertView) -> None:
        try:
            await getattr(self.api, method)(alert.id)
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"{alert.symbol} {verb}")
        await self.reload()

    def action_go_prices(self) -> None:
        self.app.switch_screen(self.app.prices_screen)

    def action_quit(self) -> None:
        self.app.exit()