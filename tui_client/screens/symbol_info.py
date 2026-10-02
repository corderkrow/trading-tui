"""Symbol info screen — quote stats + latest news for one symbol."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Static

from tui_client.widgets import BannerHeader

from tui_client.alerts.models import AlertSpec
from tui_client.alerts.screens import AlertScreen
from tui_client.api import (
    AlertApiClient,
    AlertView,
    ApiError,
    CandleView,
    NewsItemView,
    QuoteView,
    format_price,
)
from tui_client.themes import DANGER, MUTED, SUCCESS

STATS_ORDER = [
    ("Name", "name"),
    ("Price", "price"),
    ("24h Change", "change"),
    ("Volume", "volume"),
    ("Market Cap", "market_cap"),
]


class SymbolInfoScreen(Screen[None]):
    DEFAULT_CSS = """
    SymbolInfoScreen {
        background: $surface;
    }
    #info-body {
        padding: 1 3;
    }
    #info-symbol {
        background: $panel;
        color: $foreground;
        padding: 1 2;
        border: round $accent 80%;
        margin-bottom: 1;
    }
    #info-actions {
        height: auto;
        margin-bottom: 1;
    }
    #info-actions Button {
        margin-right: 1;
    }
    #alerts-title {
        color: $secondary;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    #symbol-alerts {
        height: auto;
        max-height: 10;
        border: round $secondary 40%;
        background: $surface;
        margin-bottom: 1;
    }
    #symbol-alerts > .datatable--cursor {
        background: $primary 20%;
        color: $foreground;
    }
    #alert-actions {
        height: auto;
        margin-bottom: 1;
    }
    #alert-actions Button {
        margin-right: 1;
    }
    #info-stats {
        border: round $primary 40%;
        background: $surface;
        margin-bottom: 1;
    }
    #info-stats > .datatable--odd-row {
        background: $panel 40%;
    }
    #info-stats > .datatable--even-row {
        background: $panel 15%;
    }
    #info-stats > .datatable--cursor {
        background: $primary 20%;
        color: $foreground;
    }
    #news-title {
        color: $secondary;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    #news-list {
        border: round $secondary 40%;
        background: $surface;
        padding: 1 2;
    }
    #news-list.loading {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("n", "create_alert", "New alert"),
        Binding("e", "edit_alert", "Edit"),
        Binding("x", "delete_alert", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, api: AlertApiClient, quote: QuoteView) -> None:
        super().__init__()
        self.api = api
        self.quote = quote
        self.sub_title = quote.symbol
        self._candle: CandleView | None = None
        self._candle_loaded = False
        self._alerts: list[AlertView] = []

    def compose(self) -> ComposeResult:
        yield BannerHeader()
        with VerticalScroll(id="info-body"):
            yield Static("", id="info-symbol")
            with Horizontal(id="info-actions"):
                yield Button("Create alert", id="create-alert", variant="primary")
            yield DataTable(id="info-stats")
            yield Static("[bold]Alerts[/]", id="alerts-title")
            yield DataTable(id="symbol-alerts")
            with Horizontal(id="alert-actions"):
                yield Button("Edit", id="edit-alert")
                yield Button("Delete", id="delete-alert", variant="error")
            yield Static("[bold]Latest news[/]", id="news-title")
            yield Static("", id="news-list")
        yield Footer()

    def _display_settings(self):
        user = getattr(self.app, "user", None)
        return getattr(user, "display", None) if user else None

    def on_mount(self) -> None:
        table = self.query_one("#info-stats", DataTable)
        table.add_column("", width=12)
        table.add_column("", width=40)
        table.cursor_type = "row"
        table.show_cursor = False
        table.show_header = False
        alerts = self.query_one("#symbol-alerts", DataTable)
        alerts.add_columns("Status", "Condition", "Target", "Expires")
        alerts.cursor_type = "row"
        display = self._display_settings()
        if display is not None and not display.display_news:
            self.query_one("#news-title", Static).display = False
            self.query_one("#news-list", Static).display = False
        self._render_stats()
        self.run_worker(self._load_candle())
        self.run_worker(self._load_alerts())
        self.run_worker(self._load_news())

    def _render_stats(self) -> None:
        header = self.query_one("#info-symbol", Static)
        name = f"\n[$text-muted]{self.quote.name}[/]" if self.quote.name else ""
        header.update(f"[bold $accent]{self.quote.symbol}[/]{name}")
        table = self.query_one("#info-stats", DataTable)
        table.clear()
        rows: list[tuple[str, str]] = [
            ("Price", format_price(self.quote.price)),
            ("Change 24h", self._change_value()),
        ]
        if not self._candle_loaded:
            rows.append(("OHLC", f"[{MUTED}]loading…[/]"))
        elif self._candle is None:
            rows.append(("OHLC", "—"))
        else:
            candle = self._candle
            rows += [
                ("Open", format_price(candle.open)),
                ("High", format_price(candle.high)),
                ("Low", format_price(candle.low)),
                ("Close", format_price(candle.close)),
            ]
        rows += [
            ("Volume", self.quote.volume_text()),
            ("Market Cap", self.quote.market_cap_text()),
        ]
        for label, value in rows:
            table.add_row(f"[{MUTED}]{label}[/]", value)

    def _change_value(self) -> str:
        if self.quote.change_24h is None:
            return "—"
        color, arrow = (SUCCESS, "▲") if self.quote.change_24h >= 0 else (DANGER, "▼")
        return f"[{color}]{arrow} {self.quote.change_text()}[/]"

    async def _load_candle(self) -> None:
        try:
            self._candle = await self.api.get_last_candle(self.quote.symbol)
        except Exception:
            self._candle = None
        self._candle_loaded = True
        if self.is_mounted:
            self._render_stats()

    async def _load_news(self) -> None:
        widget = self.query_one("#news-list", Static)
        display = self._display_settings()
        if display is not None and not display.display_news:
            widget.display = False
            return
        widget.remove_class("loading")
        widget.update("[$text-muted]Loading news…[/]")
        try:
            items = await self.api.get_news(self.quote.symbol, limit=display.news_per_asset if display else 10)
        except Exception as exc:
            widget.update(f"[$error]News unavailable: {getattr(exc, 'message', exc)}[/]")
            return
        self._render_news(items)

    def _render_news(self, items: list[NewsItemView]) -> None:
        widget = self.query_one("#news-list", Static)
        if not items:
            widget.update("[$text-muted]No news found for this symbol.[/]")
            return
        lines = []
        for item in items:
            publisher = f"  [$secondary]{item.publisher}[/]" if item.publisher else ""
            when = f" [dim]· {item.published_text()}[/dim]" if item.published_at else ""
            lines.append(
                f"[bold $primary]▸[/] {item.title}{publisher}{when}"
            )
        widget.update("\n\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "create-alert":
            self.action_create_alert()
        elif button_id == "edit-alert":
            self.action_edit_alert()
        elif button_id == "delete-alert":
            self.action_delete_alert()

    def _symbol_options(self) -> list[str]:
        user = getattr(self.app, "user", None)
        watchlist = user.watchlist.active_symbols() if user else []
        return list(dict.fromkeys([self.quote.symbol, *watchlist]))

    def action_create_alert(self) -> None:
        display = self._display_settings()
        if display is not None and display.disable_custom_alerts:
            self.notify("Custom alerts are disabled in settings", severity="warning")
            return
        modal = AlertScreen(
            default_symbol=self.quote.symbol,
            symbols=self._symbol_options(),
            api=self.api,
        )
        self.app.push_screen(modal, callback=self._on_alert_spec)

    def _on_alert_spec(self, spec: AlertSpec | None) -> None:
        if spec is None:
            return
        self.run_worker(self._create_alert(spec))

    async def _create_alert(self, spec: AlertSpec) -> None:
        try:
            await self.api.create_alert(spec.to_payload())
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Alert created on {spec.symbol}")
        await self._load_alerts()

    # ── existing alerts for this symbol ─────────────────────

    async def _load_alerts(self) -> None:
        try:
            alerts = await self.api.list_alerts()
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        symbol = self.quote.symbol.upper()
        self._alerts = [alert for alert in alerts if alert.symbol.upper() == symbol]
        self._render_alerts()

    def _render_alerts(self) -> None:
        # Imported lazily: prices imports this module, so a top-level import
        # would be circular.
        from tui_client.screens.prices import (
            ALERT_STATE_LABELS,
            alert_condition_cell,
            alert_meta_cell,
            alert_state_badge,
            alert_target_cell,
        )

        table = self.query_one("#symbol-alerts", DataTable)
        table.clear()
        for alert in self._alerts:
            label = ALERT_STATE_LABELS.get(alert.status, alert.status.lower())
            table.add_row(
                alert_state_badge(label, alert.status),
                alert_condition_cell(alert.condition_text()),
                alert_target_cell(alert.target_text()),
                alert_meta_cell(alert.expires_text()),
                key=alert.id,
            )
        self.query_one("#alerts-title", Static).update(
            f"[bold]Alerts[/] [{MUTED}]({len(self._alerts)})[/]"
        )

    def _selected_alert(self) -> AlertView | None:
        table = self.query_one("#symbol-alerts", DataTable)
        row = table.cursor_coordinate.row
        if 0 <= row < len(self._alerts):
            return self._alerts[row]
        return None

    def action_edit_alert(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            self.notify("Select an alert to edit", severity="warning")
            return
        modal = AlertScreen(
            symbols=self._symbol_options(),
            api=self.api,
            initial=AlertSpec.from_view(alert),
        )
        self.app.push_screen(modal, callback=lambda spec: self._on_edit_spec(alert, spec))

    def _on_edit_spec(self, alert: AlertView, spec: AlertSpec | None) -> None:
        if spec is None:
            return
        self.run_worker(self._update_alert(alert, spec))

    async def _update_alert(self, alert: AlertView, spec: AlertSpec) -> None:
        try:
            await self.api.update_alert(alert.id, spec.to_payload())
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Updated alert on {spec.symbol}")
        await self._load_alerts()

    def action_delete_alert(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            self.notify("Select an alert to delete", severity="warning")
            return
        self.run_worker(self._delete_alert(alert))

    async def _delete_alert(self, alert: AlertView) -> None:
        try:
            await self.api.delete_alert(alert.id)
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        self.notify(f"Deleted alert on {alert.symbol}")
        await self._load_alerts()

    def action_dismiss(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.run_worker(self._load_candle())
        self.run_worker(self._load_alerts())
        self.run_worker(self._load_news())
