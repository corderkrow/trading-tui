"""Symbol info screen — quote stats + latest news for one symbol."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from tui_client.widgets import BannerHeader

from tui_client.api import AlertApiClient, CandleView, NewsItemView, QuoteView, format_price

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
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, api: AlertApiClient, quote: QuoteView) -> None:
        super().__init__()
        self.api = api
        self.quote = quote
        self.sub_title = quote.symbol
        self._candle: CandleView | None = None
        self._candle_loaded = False

    def compose(self) -> ComposeResult:
        yield BannerHeader()
        with VerticalScroll(id="info-body"):
            yield Static("", id="info-symbol")
            yield DataTable(id="info-stats")
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
        display = self._display_settings()
        if display is not None and not display.display_news:
            self.query_one("#news-title", Static).display = False
            self.query_one("#news-list", Static).display = False
        self._render_stats()
        self.run_worker(self._load_candle())
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
            rows.append(("OHLC", "[#928374]loading…[/]"))
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
            table.add_row(f"[#928374]{label}[/]", value)

    def _change_value(self) -> str:
        if self.quote.change_24h is None:
            return "—"
        style = "green" if self.quote.change_24h >= 0 else "red"
        return f"[{style}]{self.quote.change_text()}[/]"

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

    def action_dismiss(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.run_worker(self._load_candle())
        self.run_worker(self._load_news())
