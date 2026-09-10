"""Prices screen — TradingView-style screener (columns, sort, pagination)."""

from __future__ import annotations

import asyncio
from math import ceil

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Label, Static, Tab, Tabs

from tui_client.widgets import BannerHeader

from tui_client.api import AlertApiClient, ApiError, CandleView, QuoteView

DEFAULT_WATCHLIST = ["BTC-USD", "ETH-USD", "SOL-USD", "AAPL", "TSLA", "NVDA"]

SCREENER_MODES: dict[str, tuple[str, str]] = {
    "t": ("most_actives", "Top (most active)"),
    "g": ("gainers", "Gainers"),
    "l": ("losers", "Losers"),
}

MARKET_TABS: list[tuple[str, str]] = [
    ("t", "Top"),
    ("g", "Gainers"),
    ("l", "Losers"),
    ("w", "Watchlist"),
    ("s", "Screener"),
    ("a", "Alerts"),
]

FILTER_SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9}

PAGE_SIZE = 25

# key -> (field on QuoteView, label)
SORT_FIELDS: dict[str, tuple[str, str]] = {
    "1": ("symbol", "Symbol"),
    "2": ("price", "Price"),
    "3": ("change_24h", "Chg%"),
    "4": ("volume", "Volume"),
    "5": ("market_cap", "Cap"),
}
# numeric columns default to descending on first press (biggest first)
DESC_FIRST = {"price", "change_24h", "volume", "market_cap"}

ALERT_STATE_LABELS = {
    "ACTIVE": "armed",
    "TRIGGERED": "triggered",
    "EXPIRED": "expired",
    "DISABLED": "idle",
}

SYMBOL_COLOR = "#83a598"

ALERT_STATE_COLORS = {
    "armed": "#b8bb26",
    "triggered": "#fabd2f",
    "expired": "#fb4934",
    "idle": "#665c54",
}

CHANGE_FILTERS: dict[str, tuple[str, str | None]] = {
    "f": ("All", None),
    "u": ("%UP", "up"),
    "d": ("%DOWN", "down"),
}


class NewWatchlistModal(ModalScreen[str | None]):
    """Ask for a watchlist name; dismisses with the name or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-body"):
            yield Label("New watchlist", id="modal-title")
            yield Input(placeholder="watchlist name…", id="wl-name")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Create", id="create", variant="primary")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wl-name":
            self._create()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "create":
            self._create()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _create(self) -> None:
        name = self.query_one("#wl-name", Input).value.strip()
        self.dismiss(name or None)


class PricesScreen(Screen[None]):
    BINDINGS = [
        Binding("t", "show_top", "Top"),
        Binding("g", "show_gainers", "Gainers"),
        Binding("l", "show_losers", "Losers"),
        Binding("w", "show_watchlist", "Watchlist"),
        Binding("s", "show_screener", "Screener"),
        Binding("1", "sort_symbol", "Sort Symbol"),
        Binding("2", "sort_price", "Sort Price"),
        Binding("3", "sort_change", "Sort Chg%"),
        Binding("4", "sort_volume", "Sort Volume"),
        Binding("5", "sort_cap", "Sort Cap"),
        Binding("[", "page_prev", "Prev"),
        Binding("]", "page_next", "Next"),
        Binding("r", "refresh", "Refresh"),
        Binding("f", "filter_all", "All"),
        Binding("u", "filter_up", "%UP"),
        Binding("d", "filter_down", "%DOWN"),
        Binding("n", "new_watchlist", "New list"),
        Binding("tab", "next_watchlist", "Next list"),
        Binding("/", "focus_search", "Search", priority=True),
        Binding("escape", "focus_table", "List"),
        Binding("a", "go_alerts", "Alerts"),
        Binding("o", "app.settings", "Settings"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        api: AlertApiClient,
        watchlist: list[str] | None = None,
        watchlists: dict[str, list[str]] | None = None,
        active_watchlist: str = "default",
        on_watchlist_change=None,
    ) -> None:
        super().__init__()
        self.api = api
        self.watchlists: dict[str, list[str]] = dict(watchlists or {"default": list(watchlist or DEFAULT_WATCHLIST)})
        if active_watchlist not in self.watchlists:
            active_watchlist = next(iter(self.watchlists))
        self.active_watchlist = active_watchlist
        self.watchlist = list(self.watchlists[self.active_watchlist])
        self.on_watchlist_change = on_watchlist_change
        self.mode: str = "t"
        self.change_filter: str | None = None
        self._quotes: list[QuoteView] = []
        self._filters: dict = {"region": "us"}
        self._screener_total: int | None = None
        self._sort_field: str | None = None
        self._sort_reverse: bool = False
        self._page: int = 1
        self._alert_states: dict[str, str] = {}
        self._candles: dict[str, CandleView] = {}
        self._search: str = ""

    def compose(self) -> ComposeResult:
        yield BannerHeader()
        yield Vertical(
            Tabs(
                *(Tab(label, id=tab_id) for tab_id, label in MARKET_TABS),
                active=self.mode,
                id="mode-tabs",
            ),
            Static("", id="watchlist-tabs"),
            Static("", id="mode-label"),
            Input(placeholder="search symbol or name…", id="search"),
            DataTable(id="prices-table"),
            id="prices-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#prices-table", DataTable)
        table.add_column("Symbol", width=8)
        table.add_column("Name", width=20)
        table.add_column("Price", width=9)
        table.add_column("Chg %", width=8)
        table.add_column("OHLC", width=58)
        table.add_column("Volume", width=10)
        table.add_column("Cap", width=10)
        table.add_column("Alert", width=10)
        table.cursor_type = "row"
        if self.mode == "s":
            self._mount_screener_input()
        self._update_mode_label()
        table.focus()
        self.run_worker(self.reload())

    def _update_tabs(self) -> None:
        tabs = self.query_one("#watchlist-tabs", Static)
        parts = []
        for name in self.watchlists:
            if name == self.active_watchlist and self.mode == "w":
                parts.append(f"[bold reverse] {name} [/]")
            else:
                parts.append(f"[dim] {name} [/]")
        filter_label, _ = CHANGE_FILTERS[self._filter_key()]
        parts.append(f"[{self._filter_color()}]{filter_label}[/]")
        tabs.update(" | ".join(parts))

    def _filter_key(self) -> str:
        for key, (_, value) in CHANGE_FILTERS.items():
            if value == self.change_filter:
                return key
        return "f"

    @staticmethod
    def _filter_color() -> str:
        return "#ebdbb2"

    def _mode_name(self) -> str:
        if self.mode == "w":
            base = f"Watchlist: {self.active_watchlist}"
        elif self.mode == "s":
            total = self._screener_total
            base = f"Screener — {total:,} matches" if total is not None else "Screener"
        else:
            base = SCREENER_MODES[self.mode][1]
        parts = [base]
        if self._sort_field:
            label = dict(SORT_FIELDS.values())[self._sort_field]
            arrow = "▼" if self._sort_reverse else "▲"
            parts.append(f"{label} {arrow}")
        total_pages = self._page_count()
        if total_pages > 1:
            parts.append(f"{self._page}/{total_pages}")
        return " · ".join(parts)

    def _page_count(self) -> int:
        return max(
            1,
            ceil(
                len(
                    [
                        q
                        for q in self._quotes
                        if self._matches_search(q) and self._matches_change_filter(q)
                    ]
                )
                / PAGE_SIZE
            ),
        )

    def _matches_search(self, quote: QuoteView) -> bool:
        if not self._search:
            return True
        haystack = quote.symbol.lower()
        if quote.name:
            haystack += " " + quote.name.lower()
        return self._search in haystack

    def _update_mode_label(self) -> None:
        self._update_tabs()
        label = self.query_one("#mode-label", Static)
        label.update(f"[bold]{self._mode_name()}[/]")

    def prepare_mode(self, mode: str) -> None:
        """Set the mode (and reset sort/page) to apply on next mount."""
        self.mode = mode
        self._sort_field = None
        self._sort_reverse = False
        self._page = 1

    def _mount_screener_input(self) -> None:
        if self.query("#filter"):
            return
        body = self.query_one("#prices-body", Vertical)
        body.mount(
            Input(
                placeholder="filtros: sector:technology mincap:1b sort:percentchange",
                id="filter",
            ),
            before="#prices-table",
        )
        self.query_one("#filter", Input).focus()

    def _set_mode(self, mode: str) -> None:
        self.prepare_mode(mode)
        tabs = self.query_one("#mode-tabs", Tabs)
        if tabs.active != mode:
            tabs.active = mode
        if mode == "s":
            self._mount_screener_input()
        elif self.query("#filter"):
            self.query_one("#filter", Input).remove()
        self._update_mode_label()
        self.run_worker(self.reload())

    @staticmethod
    def _parse_filters(text: str) -> dict:
        filters: dict = {"region": "us"}
        for token in text.split():
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            if key in ("mincap", "maxcap"):
                value = value.lower()
                if value[-1:] in FILTER_SUFFIXES:
                    filters[key] = float(value[:-1]) * FILTER_SUFFIXES[value[-1]]
                else:
                    filters[key] = float(value)
            elif key in ("region", "sector", "sort"):
                filters[key] = value
        return filters

    def _sorted(self) -> list[QuoteView]:
        if not self._sort_field:
            return list(self._quotes)
        field = self._sort_field

        def key(q: QuoteView):
            value = getattr(q, field)
            return (value is None, value if value is not None else 0)

        return sorted(self._quotes, key=key, reverse=self._sort_reverse)

    def _matches_change_filter(self, quote: QuoteView) -> bool:
        if self.change_filter is None or quote.change_24h is None:
            return self.change_filter is None
        return quote.change_24h > 0 if self.change_filter == "up" else quote.change_24h < 0

    def _rebuild_table(self) -> None:
        quotes = [
            q
            for q in self._sorted()
            if self._matches_search(q) and self._matches_change_filter(q)
        ]
        total_pages = self._page_count()
        if self._page > total_pages:
            self._page = total_pages
        start = (self._page - 1) * PAGE_SIZE
        table = self.query_one("#prices-table", DataTable)
        table.clear()
        for quote in quotes[start : start + PAGE_SIZE]:
            table.add_row(
                f"[{SYMBOL_COLOR}]{quote.symbol}[/]",
                quote.name or "—",
                quote.price_text(),
                self._change_cell(quote),
                self._ohlc_cell(quote.symbol),
                quote.volume_text(),
                quote.market_cap_text(),
                self._alert_cell(quote.symbol),
            )
        self._update_mode_label()

    async def reload(self) -> None:
        try:
            alerts = await self.api.list_alerts()
            self._alert_states = {}
            for alert in alerts:
                label = ALERT_STATE_LABELS.get(alert.status, alert.status.lower())
                if label != "armed" or alert.symbol not in self._alert_states:
                    self._alert_states[alert.symbol] = label
            if self.mode == "w":
                if not self.watchlist:
                    self._quotes = []
                else:
                    self._quotes = await self.api.get_quotes(self.watchlist)
            elif self.mode == "s":
                filters = {k: v for k, v in self._filters.items() if v is not None}
                sort = filters.pop("sort", "marketcap")
                result = await self.api.search_screeners(filters, size=250, sort=sort)
                self._quotes = result.quotes
                self._screener_total = result.total
            else:
                scr_id = SCREENER_MODES[self.mode][0]
                self._quotes = await self.api.get_screeners(scr_id, count=250)
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        await self._load_candles()
        self._rebuild_table()

    async def _load_candles(self) -> None:
        """Fetch latest candle per row on the current page; cache by symbol."""
        page = min(self._page, self._page_count())
        start = (page - 1) * PAGE_SIZE
        page_symbols = [q.symbol for q in self._quotes[start : start + PAGE_SIZE]]
        missing = [s for s in page_symbols if s not in self._candles]
        if not missing:
            return
        results = await asyncio.gather(
            *(self.api.get_last_candle(s) for s in missing),
            return_exceptions=True,
        )
        for symbol, result in zip(missing, results):
            if isinstance(result, CandleView):
                self._candles[symbol] = result

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.mode == "s" and event.input.id == "filter":
            self._filters = self._parse_filters(event.value)
            self._screener_total = None
            self._page = 1
            self.query_one("#prices-table", DataTable).focus()
            self.run_worker(self.reload())

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if not tab_id or tab_id == self.mode:
            return
        if tab_id == "a":
            self.query_one("#mode-tabs", Tabs).active = self.mode
            self.app.switch_screen(self.app.alerts_screen)
            return
        self._set_mode(tab_id)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._search = event.value.strip().lower()
            self._page = 1
            self._rebuild_table()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_table(self) -> None:
        self.query_one("#prices-table", DataTable).focus()

    def _sort(self, field: str) -> None:
        if self._sort_field == field:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_field = field
            self._sort_reverse = field in DESC_FIRST
        self._page = 1
        self._rebuild_table()

    def action_sort_symbol(self) -> None:
        self._sort("symbol")

    def action_sort_price(self) -> None:
        self._sort("price")

    def action_sort_change(self) -> None:
        self._sort("change_24h")

    def action_sort_volume(self) -> None:
        self._sort("volume")

    def action_sort_cap(self) -> None:
        self._sort("market_cap")

    def action_page_prev(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._rebuild_table()

    def action_page_next(self) -> None:
        if self._page < self._page_count():
            self._page += 1
            self._rebuild_table()

    def _alert_cell(self, symbol: str) -> str:
        label = self._alert_states.get(symbol)
        if not label:
            return ""
        color = ALERT_STATE_COLORS.get(label, "#ebdbb2")
        return f"[{color}]{label}[/]"

    def _ohlc_cell(self, symbol: str) -> str:
        candle = self._candles.get(symbol)
        return candle.ohlc_text() if candle is not None else "—"

    @staticmethod
    def _change_cell(quote: QuoteView) -> str:
        if quote.change_24h is None:
            return "—"
        style = "green" if quote.change_24h >= 0 else "red"
        return f"[{style}]{quote.change_text()}[/]"

    def action_show_top(self) -> None:
        self._set_mode("t")

    def action_show_gainers(self) -> None:
        self._set_mode("g")

    def action_show_losers(self) -> None:
        self._set_mode("l")

    def action_show_watchlist(self) -> None:
        self._set_mode("w")

    def action_next_watchlist(self) -> None:
        if self.mode != "w" or len(self.watchlists) < 2:
            return
        names = list(self.watchlists)
        idx = names.index(self.active_watchlist)
        self._switch_watchlist(names[(idx + 1) % len(names)])

    def _switch_watchlist(self, name: str) -> None:
        self.active_watchlist = name
        self.watchlist = list(self.watchlists[name])
        self._page = 1
        if self.mode != "w":
            self._set_mode("w")
        else:
            self.run_worker(self.reload())

    def _filter_by_key(self, key: str) -> None:
        self.change_filter = CHANGE_FILTERS[key][1]
        self._page = 1
        self._rebuild_table()

    def action_filter_all(self) -> None:
        self._filter_by_key("f")

    def action_filter_up(self) -> None:
        self._filter_by_key("u")

    def action_filter_down(self) -> None:
        self._filter_by_key("d")

    def action_new_watchlist(self) -> None:
        self.app.push_screen(NewWatchlistModal(), callback=self._on_new_watchlist)

    def _on_new_watchlist(self, name: str | None) -> None:
        if not name:
            return
        if name in self.watchlists:
            self.notify(f"Watchlist '{name}' already exists", severity="warning")
            return
        self.watchlists[name] = []
        if self.on_watchlist_change is not None:
            self.on_watchlist_change(name, [])
        self._switch_watchlist(name)

    def action_show_screener(self) -> None:
        self._set_mode("s")

    def action_refresh(self) -> None:
        self.run_worker(self.reload())

    def action_go_alerts(self) -> None:
        self.app.switch_screen(self.app.alerts_screen)

    def action_quit(self) -> None:
        self.app.exit()