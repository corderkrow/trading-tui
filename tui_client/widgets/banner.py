"""Custom widgets for the TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Header
from textual.widgets._header import HeaderIcon, HeaderTitle

# gruvbox dark palette (matches install.sh banner)

# nf-md-candle — nerd font candlestick chart glyph
_ICON = "\U000F1A0C"


class BannerHeader(Header):
    """Header styled like the install.sh gruvbox banner card."""

    DEFAULT_CSS = """
    BannerHeader {
        height: 2;
        background: $background;
    }
    BannerHeader > HeaderIcon {
        color: $primary;
    }
    BannerHeader > HeaderTitle {
        text-align: left;
        color: $primary;
        text-style: bold;
    }
    """

    def _on_click(self, event) -> None:
        event.stop()
        event.prevent_default()

    def format_title(self):
        from textual.content import Content

        title = self.screen_title or ""
        sub = self.screen_sub_title or ""
        markup = f"[bold $primary]{title}[/bold $primary] [$secondary] · {sub}[/$secondary]"
        return Content.from_markup(markup)

    def compose(self) -> ComposeResult:
        icon = HeaderIcon()
        icon.icon = _ICON
        yield icon
        yield HeaderTitle()
