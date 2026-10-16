"""Alert list screen — keyboard-driven table of alerts."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, Tab, Tabs

from tui_client.alerts.models import AlertSpec
from tui_client.alerts.screens import AlertScreen
from tui_client.api import AlertApiClient, AlertEventView, AlertView, ApiError
from tui_client.screens.prices import (
    ALERT_STATE_LABELS,
    MARKET_TABS,
    alert_condition_cell,
    alert_meta_cell,
    alert_state_badge,
    alert_symbol_cell,
    alert_target_cell,
)
from tui_client.widgets import BannerHeader


class AlertListScreen(Screen[None]):
    TITLE = "Alerts"
    SUB_TITLE = "price alerts"

    BINDINGS = [
        Binding("n", "new_alert", "New"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "enable", "Enable"),
        Binding("d", "disable", "Disable"),
        Binding("x", "delete", "Delete"),
        Binding("p", "go_prices", "Prices"),
        Binding("tab", "next_list", "Next list"),
        Binding("o", "app.settings", "Settings"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, api: AlertApiClient, default_symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.api = api
        self.default_symbol = default_symbol
        self._alerts: list[AlertView] = []
        self._events: list[AlertEventView] = []
        self._seen_event_ids: set[str] = set()
        self._primed = False

    def compose(self) -> ComposeResult:
        yield BannerHeader()
        yield Tabs(
            *(Tab(label, id=tab_id) for tab_id, label in MARKET_TABS),
            active="a",
            id="mode-tabs",
        )
        yield DataTable(id="alerts-table")
        yield Static("Loading alerts…", id="alerts-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("Symbol", "Condition", "Target", "Message", "Status", "Expires")
        table.cursor_type = "row"
        table.focus()
        self.run_worker(self.reload())
        # Stored alerts fire server-side now; keep the table and the event
        # feed fresh without manual `r` presses.
        self.set_interval(15.0, self._auto_refresh)

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
            table.add_row(
                alert_symbol_cell(alert.symbol),
                alert_condition_cell(alert.condition_text()),
                alert_target_cell(alert.target_text()),
                alert_meta_cell(escape(alert.message) if alert.message else "—"),
                alert_state_badge(status_label, alert.status),
                alert_meta_cell(alert.expires_text()),
            )
        self.sub_title = f"{len(self._alerts)} price alert(s)"
        hint = self.query_one("#alerts-hint", Static)
        if self._alerts:
            hint.update(
                f"{len(self._alerts)} alert(s) · n new · enter/dbl-click edit · "
                "e/d toggle · x delete · r refresh"
            )
        else:
            hint.update("No alerts yet — press n to create one")

    async def _auto_refresh(self) -> None:
        """Poll alerts + event feed; toast on events the user hasn't seen."""
        await self.reload()
        list_events = getattr(self.api, "list_events", None)
        if list_events is None:
            return  # client without the events endpoint (test fakes)
        try:
            self._events = await list_events(limit=50)
        except ApiError:
            return  # feed is best-effort; alerts table already updated
        for event in self._events:
            key = f"{event.alert_id}:{event.triggered_at}"
            if key in self._seen_event_ids:
                continue
            self._seen_event_ids.add(key)
            if self._primed:
                self.notify(f"🔔 {event.message}", timeout=6)
        self._primed = True

    def on_screen_resume(self) -> None:
        """Re-arm the Alerts tab when returning to this screen.

        Activating a markets tab while Alerts is mounted leaves that tab marked
        active in the installed screen, so re-entering would otherwise show the
        stale selection instead of Alerts.
        """
        tabs = self.query_one("#mode-tabs", Tabs)
        if tabs.active != "a":
            tabs.active = "a"

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if not self.is_mounted:
            return
        tab_id = event.tab.id
        if not tab_id or tab_id == "a":
            return
        prices = self.app.prices_screen
        prices.activate_mode(tab_id)
        self.app.switch_screen("prices")

    def _symbol_options(self, *extra: str) -> list[str]:
        """Dialog symbol list: the alert's symbol, then the active watchlist."""
        watchlist = self.app.user.watchlist.active_symbols()
        return list(dict.fromkeys([*extra, self.default_symbol, *watchlist]))

    def action_new_alert(self) -> None:
        display = getattr(self.app.user, "display", None)
        if display is not None and display.disable_custom_alerts:
            self.notify("Custom alerts are disabled in settings", severity="warning")
            return
        modal = AlertScreen(
            default_symbol=self.default_symbol,
            symbols=self._symbol_options(),
            api=self.api,
        )
        self.app.push_screen(modal, callback=self._on_modal_result)

    def _on_modal_result(self, spec: AlertSpec | None) -> None:
        if spec is None:
            return
        self.run_worker(self._create(spec))

    async def _create(self, spec: AlertSpec) -> None:
        try:
            await self.api.create_alert(spec.to_payload())
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Alert created on {spec.symbol}")
        await self.reload()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter or double-click on a row opens the alert for editing."""
        row = event.cursor_row
        if row < 0 or row >= len(self._alerts):
            return
        self._open_editor(self._alerts[row])

    def _open_editor(self, alert: AlertView) -> None:
        modal = AlertScreen(
            symbols=self._symbol_options(alert.symbol),
            api=self.api,
            initial=AlertSpec.from_view(alert),
        )
        self.app.push_screen(modal, callback=lambda spec: self._on_edit_result(alert, spec))

    def _on_edit_result(self, alert: AlertView, spec: AlertSpec | None) -> None:
        if spec is None:
            return
        self.run_worker(self._update(alert, spec))

    async def _update(self, alert: AlertView, spec: AlertSpec) -> None:
        try:
            await self.api.update_alert(alert.id, spec.to_payload())
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Updated alert on {spec.symbol}")
        await self.reload()


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
        self.app.switch_screen("prices")

    def action_next_list(self) -> None:
        """`tab`: leave Alerts and wrap to the first top-level tab."""
        prices = self.app.prices_screen
        prices.activate_mode("t")
        self.app.switch_screen("prices")

    def action_quit(self) -> None:
        self.app.exit()