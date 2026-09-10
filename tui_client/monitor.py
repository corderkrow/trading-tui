"""Background price-change monitor — TUI-side, threshold-driven toasts.

Polls quotes for the configured sources (watchlist / portfolio / both) and
fires a callback when a symbol's 24h change crosses an enabled percentage
threshold (entering the zone re-arms only after falling back below it).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from tui_client.api import ApiError, QuoteView
from tui_client.settings import UserSettings

POLL_SECONDS = 60

EventHandler = Callable[[str, float, float], Awaitable[None]]


class PriceChangeMonitor:
    def __init__(
        self,
        api,
        settings_provider: Callable[[], UserSettings],
        on_event: EventHandler,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self.api = api
        self.settings_provider = settings_provider
        self.on_event = on_event
        self.poll_seconds = poll_seconds
        # (symbol, threshold) -> was in threshold zone last poll
        self._zone: dict[tuple[str, float], bool] = {}

    def source_symbols(self) -> list[str]:
        settings = self.settings_provider()
        sources = settings.notifications.price_change_sources
        if sources == "portfolio":
            return []  # no portfolio feature yet
        return settings.watchlist.active_symbols()  # watchlist / both (both ⊇ watchlist)

    async def poll_once(self) -> list[tuple[str, float, float]]:
        """Return (symbol, change, threshold) triples fired this cycle."""
        settings = self.settings_provider()
        thresholds = settings.notifications.enabled_thresholds()
        quotes = await self.api.get_quotes(self.source_symbols())
        fired: list[tuple[str, float, float]] = []
        for quote in quotes:
            change = quote.change_24h
            if change is None:
                continue
            for threshold in thresholds:
                key = (quote.symbol, threshold)
                was_in = self._zone.get(key, False)
                is_in = abs(change) >= threshold
                self._zone[key] = is_in
                if is_in and not was_in:
                    fired.append((quote.symbol, change, threshold))
                    await self.on_event(quote.symbol, change, threshold)
        return fired

    async def run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except ApiError:
                pass  # transient API failures — retry next cycle
            await asyncio.sleep(self.poll_seconds)


def event_message(symbol: str, change: float, threshold: float) -> str:
    return f"{symbol} moved {change:+.2f}% (≥ {threshold:g}% threshold)"
