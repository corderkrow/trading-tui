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
        background: #282828;
    }
    BannerHeader > HeaderIcon {
        color: #b8bb26;
    }
    BannerHeader > HeaderTitle {
        text-align: left;
        color: #b8bb26;
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
        markup = f"[bold #b8bb26]{title}[/bold #b8bb26] [#8ec07c] · {sub}[/#8ec07c]"
        return Content.from_markup(markup)

    def compose(self) -> ComposeResult:
        icon = HeaderIcon()
        icon.icon = _ICON
        yield icon
        yield HeaderTitle()
