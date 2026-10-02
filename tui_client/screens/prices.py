"""Prices screen — TradingView-style screener (columns, sort, pagination)."""

from __future__ import annotations

import asyncio
import time
from math import ceil

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Label, Select, Static, Tab, Tabs

from tui_client.widgets import BannerHeader, SymbolAutoComplete

from tui_client.api import AlertApiClient, ApiError, CandleView, QuoteView, SearchHitView
from tui_client.screens.symbol_info import SymbolInfoScreen
from tui_client.themes import BG, CYAN, DANGER, INK, MUTED, SUCCESS, TEAL_LIGHT, WARNING

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

SYMBOL_COLOR = TEAL_LIGHT

# Filled pill per state — (foreground, background). A background fill reads
# faster than coloured text alone, so armed / triggered / expired / idle stay
# distinct even when rows sit next to each other.
ALERT_STATE_BADGES = {
    "armed": (BG, CYAN),
    "triggered": (BG, WARNING),
    "expired": (BG, DANGER),
    "idle": (BG, MUTED),
}


def alert_state_badge(label: str, text: str | None = None) -> str:
    """Filled pill for a UI state label; `text` overrides the displayed word."""
    fg, bg = ALERT_STATE_BADGES.get(label, (INK, MUTED))
    return f"[{fg} on {bg}]{text if text is not None else label}[/]"


def alert_symbol_cell(symbol: str) -> str:
    """Ticker cell — brand accent, matching prices-table symbols."""
    return f"[{SYMBOL_COLOR}]{symbol}[/]"


def alert_condition_cell(text: str) -> str:
    """Operator label — muted; the target value carries the row's emphasis."""
    return f"[{MUTED}]{text}[/]"


def alert_target_cell(text: str) -> str:
    """Trigger value — bold ink, the number the alert fires on."""
    return f"[bold]{text}[/]"


def alert_meta_cell(text: str) -> str:
    """Message / expiry — muted secondary text."""
    return f"[{MUTED}]{text}[/]"

CHANGE_FILTERS: dict[str, tuple[str, str | None]] = {
    "f": ("All", None),
    "u": ("%UP", "up"),
    "d": ("%DOWN", "down"),
}


class NameModal(ModalScreen[str | None]):
    """Ask for a watchlist name; dismisses with the name or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        value: str = "",
        submit_label: str = "Create",
        placeholder: str = "watchlist name…",
    ) -> None:
        super().__init__()
        self._title = title
        self._value = value
        self._submit_label = submit_label
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-body"):
            yield Label(self._title, id="modal-title")
            yield Input(value=self._value, placeholder=self._placeholder, id="wl-name")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button(self._submit_label, id="create", variant="primary")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wl-name":
            self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "create":
            self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        name = self.query_one("#wl-name", Input).value.strip()
        self.dismiss(name or None)


class AddSymbolModal(ModalScreen[tuple[str, str] | None]):
    """Pick a symbol and the watchlist to add it to; dismisses with (name, symbol).

    Without ``allow_list_choice`` the watchlist is fixed to ``target`` and the
    modal behaves as a plain symbol prompt.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        api: AlertApiClient | None = None,
        symbols: list[str] | None = None,
        title: str = "Add symbol",
        watchlists: list[str] | None = None,
        target: str | None = None,
        allow_list_choice: bool = False,
    ) -> None:
        super().__init__()
        self._api = api
        self._symbols = list(dict.fromkeys(symbols or []))
        self._title = title
        self._names = list(dict.fromkeys(watchlists or []))
        self._target = target
        self._allow_list_choice = allow_list_choice
        self._autocomplete: SymbolAutoComplete | None = None
        self._search_timer = None

    def compose(self) -> ComposeResult:
        symbol_input = Input(
            placeholder="symbol…", id="wl-symbol", restrict=r"[A-Za-z0-9.\-]*"
        )
        with Vertical(id="modal-body"):
            yield Label(self._title, id="modal-title")
            yield symbol_input
            if self._allow_list_choice:
                yield Label("Add to watchlist", classes="field-label")
                options = [(name, name) for name in self._names]
                current = self._target or (self._names[0] if self._names else "")
                yield Select(options, value=current or Select.BLANK, id="wl-target")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Add", id="add", variant="primary")
        self._autocomplete = SymbolAutoComplete(
            symbol_input, id="wl-symbol-autocomplete", on_selected=self._on_selected
        )
        yield self._autocomplete

    def on_mount(self) -> None:
        if self._autocomplete is not None:
            self._autocomplete.set_hits(
                [SearchHitView(symbol=s, name="") for s in self._symbols]
            )
        self.query_one("#wl-symbol", Input).focus()

    def _on_selected(self, symbol: str) -> None:
        if self._autocomplete is not None:
            self._autocomplete.set_hits([])

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "wl-symbol":
            return
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
        term = event.value.strip()
        if term:
            self._search_timer = self.set_timer(
                0.3, lambda: self.run_worker(self._search(term))
            )

    async def _search(self, term: str) -> None:
        """Fetch symbol suggestions for the input from the search endpoint."""
        self._search_timer = None
        if self._api is None or self._autocomplete is None or not self.is_mounted:
            return
        try:
            hits = await self._api.search_symbols(term)
        except ApiError:
            return
        except Exception as exc:  # transport errors must not surface as a crash
            self.log.warning(f"symbol search failed: {exc!r}")
            return
        if not self.is_mounted:
            return
        current = self.query_one("#wl-symbol", Input).value.strip()
        if current != term:
            return
        local = [
            SearchHitView(symbol=s, name="")
            for s in self._symbols
            if term.lower() in s.lower()
        ]
        self._autocomplete.set_hits([*hits, *local])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "wl-symbol":
            self._add()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "add":
            self._add()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _add(self) -> None:
        symbol = self.query_one("#wl-symbol", Input).value.strip().upper()
        if not symbol:
            return
        target = self._target
        if self._allow_list_choice:
            value = self.query_one("#wl-target", Select).value
            target = value if isinstance(value, str) else self._names[0]
        if not target:
            return
        self.dismiss((target, symbol))


class ConfirmModal(ModalScreen[bool]):
    """Yes/no confirmation; dismisses with True (confirm) or False."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question: str, confirm_label: str = "Delete") -> None:
        super().__init__()
        self._question = question
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-body"):
            yield Label(self._question, id="modal-title")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button(self._confirm_label, id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(False)
        elif event.button.id == "confirm":
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PricesScreen(Screen[None]):
    TITLE = "Markets"
    SUB_TITLE = "live quotes"

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
        Binding("e", "edit_watchlist", "Edit list"),
        Binding("D", "delete_watchlist", "Del list"),
        Binding("plus", "add_symbol", "+ Symbol"),
        Binding("x", "remove_symbol", "- Symbol"),
        Binding("delete", "remove_symbol", "- Symbol"),
        Binding("backspace", "remove_symbol", "- Symbol"),
        Binding("ctrl+h", "remove_symbol", "- Symbol"),
        Binding("minus", "remove_symbol", "- Symbol"),
        Binding("tab", "next_list", "Next list"),
        Binding("ctrl+right", "next_watchlist", "Next watchlist"),
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
        watchlist_mode: str = "single",
        display=None,
    ) -> None:
        super().__init__()
        self.api = api
        self.watchlists: dict[str, list[str]] = dict(watchlists or {"default": list(watchlist or DEFAULT_WATCHLIST)})
        if active_watchlist not in self.watchlists:
            active_watchlist = next(iter(self.watchlists))
        self.active_watchlist = active_watchlist
        self.watchlist = list(self.watchlists[self.active_watchlist])
        self.on_watchlist_change = on_watchlist_change
        self.watchlist_mode = watchlist_mode
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
        self._candles_at: float = 0.0
        self._search: str = ""
        self._server_search: bool = False
        self._search_timer = None
        self._refresh_timer = None
        self._rotation_timer = None
        self._display = display

    def apply_display(self, display) -> None:
        """Restart the auto-refresh + rotation intervals from display settings."""
        self._display = display
        self._start_refresh_timer()
        self._start_rotation_timer()

    def _start_refresh_timer(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        self._refresh_timer = self.set_timer(self._display.refresh_interval_minutes * 60, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._start_refresh_timer()
        self.run_worker(self.reload())

    def _start_rotation_timer(self) -> None:
        if self._rotation_timer is not None:
            self._rotation_timer.stop()
            self._rotation_timer = None
        if self._display is None:
            return
        self._rotation_timer = self.set_timer(
            self._display.stock_rotation_interval, self._rotate_watchlist
        )

    def _rotate_watchlist(self) -> None:
        self._start_rotation_timer()
        if self.mode == "w" and self.is_running:
            self._switch_watchlist_next()

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
        table.add_column("OHLC", width=64)
        table.add_column("Volume", width=10)
        table.add_column("Cap", width=10)
        table.add_column("Alert", width=10)
        table.cursor_type = "row"
        if self.mode == "s":
            self._mount_screener_input()
        self._update_mode_label()
        table.focus()
        self.run_worker(self.reload())
        if self._display is not None:
            self._start_refresh_timer()
            self._start_rotation_timer()

    def on_key(self, event) -> None:
        """Catch every terminal flavour of the delete key for symbol removal.

        Terminals send different codes for the key labelled Delete/Backspace
        (`delete`, `backspace`, `ctrl+h`, `minus`, shift/ctrl variants), so match
        on the key name instead of binding each one individually.
        """
        if self.mode != "w":
            return
        key = event.key
        if key == "minus" or "delete" in key or "backspace" in key or key == "ctrl+h":
            event.stop()
            event.prevent_default()
            self.action_remove_symbol()

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
        return INK

    def _mode_name(self, total_quotes: int | None = None) -> str:
        if self.mode == "w":
            base = f"Watchlist: {self.active_watchlist}"
        elif self.mode == "s":
            total = self._screener_total
            base = f"Screener — {total:,} matches" if total is not None else "Screener"
        else:
            base = SCREENER_MODES[self.mode][1]
        parts = [base]
        if self.mode == "s":
            parts.append("/ to filter")
        if self._sort_field:
            label = dict(SORT_FIELDS.values())[self._sort_field]
            arrow = "▼" if self._sort_reverse else "▲"
            parts.append(f"{label} {arrow}")
        total_pages = self._page_count(total_quotes)
        if total_pages > 1:
            parts.append(f"{self._page}/{total_pages}")
        return " · ".join(parts)

    def _page_count(self, total_quotes: int | None = None) -> int:
        """Page count; pass `total_quotes` to reuse an already-filtered list."""
        if total_quotes is None:
            total_quotes = len(
                [
                    q
                    for q in self._quotes
                    if self._matches_search(q) and self._matches_change_filter(q)
                ]
            )
        return max(1, ceil(total_quotes / PAGE_SIZE))

    def _matches_search(self, quote: QuoteView) -> bool:
        if self._server_search:
            return True
        if not self._search:
            return True
        haystack = quote.symbol.lower()
        if quote.name:
            haystack += " " + quote.name.lower()
        return self._search in haystack

    def _update_mode_label(self, total_quotes: int | None = None) -> None:
        self._update_tabs()
        label = self.query_one("#mode-label", Static)
        label.update(f"[bold]{self._mode_name(total_quotes)}[/]")

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
        self.query_one("#prices-table", DataTable).focus()

    def activate_mode(self, mode: str) -> None:
        """Switch to `mode`, syncing the tab bar, label and data."""
        self._set_mode(mode)

    def _reset_search(self) -> None:
        """Drop the active search term and clear the search box."""
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None
        self._search = ""
        self._server_search = False
        if self.is_mounted and self.query("#search"):
            self.query_one("#search", Input).value = ""

    def _set_mode(self, mode: str) -> None:
        if not self.is_mounted:
            self.prepare_mode(mode)
            return
        self.prepare_mode(mode)
        self._reset_search()
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
        total_pages = self._page_count(len(quotes))
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
                key=quote.symbol,
            )
        self._update_mode_label(len(quotes))

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

    def _candle_ttl(self) -> float:
        """Candles go stale with the quote refresh cadence (5 min fallback)."""
        if self._display is not None:
            return self._display.refresh_interval_minutes * 60
        return 300.0

    async def _load_candles(self) -> None:
        """Fetch latest candle per row on the current page; cache by symbol."""
        page = min(self._page, self._page_count())
        start = (page - 1) * PAGE_SIZE
        page_symbols = [q.symbol for q in self._quotes[start : start + PAGE_SIZE]]
        stale = time.monotonic() - self._candles_at > self._candle_ttl()
        missing = [s for s in page_symbols if stale or s not in self._candles]
        if not missing:
            return
        results = await asyncio.gather(
            *(self.api.get_last_candle(s) for s in missing),
            return_exceptions=True,
        )
        refreshed = False
        for symbol, result in zip(missing, results):
            if isinstance(result, CandleView):
                self._candles[symbol] = result
                refreshed = True
        if refreshed:
            self._candles_at = time.monotonic()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            if self._search_timer is not None:
                self._search_timer.stop()
                self._search_timer = None
            if self._search:
                self.run_worker(self._run_server_search())
            self.query_one("#prices-table", DataTable).focus()
        elif self.mode == "s" and event.input.id == "filter":
            self._filters = self._parse_filters(event.value)
            self._screener_total = None
            self._page = 1
            self.query_one("#prices-table", DataTable).focus()
            self.run_worker(self.reload())

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if not self.is_mounted:
            return
        tab_id = event.tab.id
        if not tab_id or tab_id == self.mode:
            return
        if tab_id == "a":
            self.query_one("#mode-tabs", Tabs).active = self.mode
            self.app.switch_screen("alerts")
            return
        self._set_mode(tab_id)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._search = event.value.strip().lower()
            self._page = 1
            if not self._search:
                if self._search_timer is not None:
                    self._search_timer.stop()
                    self._search_timer = None
                # A server search replaced `_quotes` with just the matches, so
                # clearing must re-fetch the mode's full result set.
                if self._server_search:
                    self._server_search = False
                    self.run_worker(self.reload())
                else:
                    self._rebuild_table()
                return
            if self._search_timer is not None:
                self._search_timer.stop()
            self._search_timer = self.set_timer(0.4, self._run_server_search)

    async def _run_server_search(self) -> None:
        """Look the search term up on the exchange, then show matched quotes."""
        self._search_timer = None
        term = self._search
        if not term:
            return
        try:
            hits = await self.api.search_symbols(term)
            symbols = [hit.symbol for hit in hits]
            quotes = await self.api.get_quotes(symbols) if symbols else []
        except ApiError as exc:
            self.notify(exc.message, severity="error")
            return
        if term != self._search:
            return
        self._server_search = True
        self._quotes = quotes
        self._page = 1
        self._rebuild_table()

    def action_focus_search(self) -> None:
        if self.mode == "s" and self.query("#filter"):
            self.query_one("#filter", Input).focus()
            return
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
        return alert_state_badge(label)

    def _ohlc_cell(self, symbol: str) -> str:
        candle = self._candles.get(symbol)
        return candle.ohlc_text() if candle is not None else "—"

    @staticmethod
    def _change_cell(quote: QuoteView) -> str:
        if quote.change_24h is None:
            return "—"
        color, arrow = (SUCCESS, "▲") if quote.change_24h >= 0 else (DANGER, "▼")
        return f"[{color}]{arrow} {quote.change_text()}[/]"

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open symbol info (click or Enter) with stats + latest news."""
        symbol = event.row_key.value
        if not symbol:
            return
        quote = next((q for q in self._quotes if q.symbol == symbol), None)
        if quote is None:
            return
        self.app.push_screen(SymbolInfoScreen(self.api, quote))

    def action_show_top(self) -> None:
        self._set_mode("t")

    def action_show_gainers(self) -> None:
        self._set_mode("g")

    def action_show_losers(self) -> None:
        self._set_mode("l")

    def action_show_watchlist(self) -> None:
        self._set_mode("w")

    def action_next_list(self) -> None:
        """`tab`: advance to the next top-level tab, wrapping past Alerts."""
        ids = [tab_id for tab_id, _ in MARKET_TABS]
        self._activate_mode(ids[(ids.index(self.mode) + 1) % len(ids)])

    def _activate_mode(self, mode: str) -> None:
        """Switch to a top-level tab, including the Alerts screen."""
        if mode == "a":
            self.app.switch_screen("alerts")
            return
        self._set_mode(mode)

    def action_next_watchlist(self) -> None:
        if self.watchlist_mode != "multiple" or self.mode != "w":
            return
        self._switch_watchlist_next()

    def _switch_watchlist_next(self) -> None:
        if len(self.watchlists) < 2:
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
        if self.watchlist_mode != "multiple":
            self.notify(
                "Watchlist mode is 'single' — enable multiple watchlists in settings.",
                severity="warning",
            )
            return
        self.app.push_screen(
            NameModal("New watchlist", submit_label="Create"),
            callback=self._on_new_watchlist,
        )

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

    def action_edit_watchlist(self) -> None:
        if self.watchlist_mode != "multiple":
            self.notify(
                "Watchlist mode is 'single' — enable multiple watchlists in settings.",
                severity="warning",
            )
            return
        self.app.push_screen(
            NameModal(
                "Rename watchlist",
                value=self.active_watchlist,
                submit_label="Rename",
            ),
            callback=self._on_edit_watchlist,
        )

    def _on_edit_watchlist(self, name: str | None) -> None:
        old = self.active_watchlist
        if not name or name == old:
            return
        if name in self.watchlists:
            self.notify(f"Watchlist '{name}' already exists", severity="warning")
            return
        renamed = {
            (name if key == old else key): list(symbols)
            for key, symbols in self.watchlists.items()
        }
        self.watchlists = renamed
        self.active_watchlist = name
        self.watchlist = list(renamed[name])
        if self.on_watchlist_change is not None:
            self.on_watchlist_change(old, None)
            self.on_watchlist_change(name, self.watchlist)
        self.run_worker(self.reload())
        self.notify(f"Renamed '{old}' to '{name}'")

    def action_delete_watchlist(self) -> None:
        if self.watchlist_mode != "multiple":
            self.notify(
                "Watchlist mode is 'single' — enable multiple watchlists in settings.",
                severity="warning",
            )
            return
        if len(self.watchlists) < 2:
            self.notify("Cannot delete the last watchlist", severity="warning")
            return
        self.app.push_screen(
            ConfirmModal(f"Delete watchlist '{self.active_watchlist}'?"),
            callback=self._on_delete_watchlist,
        )

    def _on_delete_watchlist(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        removed = self.active_watchlist
        del self.watchlists[removed]
        if self.on_watchlist_change is not None:
            self.on_watchlist_change(removed, None)
        self._switch_watchlist(next(iter(self.watchlists)))
        self.notify(f"Deleted watchlist '{removed}'")

    def _target_watchlist_for(self, symbol: str) -> str:
        """First watchlist already holding ``symbol``; otherwise the active one."""
        for name, symbols in self.watchlists.items():
            if symbol in symbols:
                return name
        return self.active_watchlist

    def _set_active_symbols(self, symbols: list[str]) -> None:
        """Replace the active watchlist's symbols, persist, and reload the table."""
        self.watchlists[self.active_watchlist] = list(symbols)
        self.watchlist = list(symbols)
        if self.on_watchlist_change is not None:
            self.on_watchlist_change(self.active_watchlist, list(symbols))
        self._page = 1
        self.run_worker(self.reload())

    def action_add_symbol(self) -> None:
        if self.mode != "w":
            self.notify("Switch to Watchlist to add a symbol", severity="warning")
            return
        self.app.push_screen(
            AddSymbolModal(
                self.api,
                self.watchlist,
                title="Add symbol",
                watchlists=list(self.watchlists),
                target=self.active_watchlist,
                allow_list_choice=True,
            ),
            callback=self._on_add_symbol,
        )

    def _on_add_symbol(self, result: tuple[str, str] | None) -> None:
        if not result:
            return
        name, symbol = result
        symbol = symbol.strip().upper()
        if not symbol:
            return
        if name not in self.watchlists:
            self.notify(f"Watchlist '{name}' no longer exists", severity="warning")
            return
        if symbol in self.watchlists[name]:
            self.notify(f"{symbol} already in {name}", severity="warning")
            return
        if name == self.active_watchlist:
            self._set_active_symbols([*self.watchlist, symbol])
        else:
            updated = [*self.watchlists[name], symbol]
            self.watchlists[name] = updated
            if self.on_watchlist_change is not None:
                self.on_watchlist_change(name, updated)
            self.notify(f"Added {symbol} to {name}")

    def _selected_symbol(self) -> str | None:
        table = self.query_one("#prices-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value or None

    def action_remove_symbol(self) -> None:
        if self.mode != "w":
            self.notify("Switch to Watchlist to remove a symbol", severity="warning")
            return
        symbol = self._selected_symbol()
        if not symbol:
            return
        # Remove from every watchlist that holds it, so a symbol shown in a
        # search result can be dropped even when it lives on another list.
        holders = [n for n, syms in self.watchlists.items() if symbol in syms]
        if not holders:
            self.notify(f"{symbol} not in any watchlist", severity="warning")
            return
        for name in holders:
            self.watchlists[name] = [s for s in self.watchlists[name] if s != symbol]
            if self.on_watchlist_change is not None:
                self.on_watchlist_change(name, self.watchlists[name])
        self.watchlist = list(self.watchlists[self.active_watchlist])
        if self._server_search:
            self._quotes = [q for q in self._quotes if q.symbol != symbol]
            self._rebuild_table()
        else:
            self._page = 1
            self.run_worker(self.reload())
        self.notify(f"Removed {symbol} from {', '.join(holders)}")

    def action_show_screener(self) -> None:
        self._set_mode("s")

    def action_refresh(self) -> None:
        self.run_worker(self.reload())

    def action_go_alerts(self) -> None:
        self.app.switch_screen("alerts")

    def action_quit(self) -> None:
        self.app.exit()